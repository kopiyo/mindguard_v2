"""
app.py — MindGuard Canonical Streamlit Entrypoint
Merged from: Try_streamlit_app.py · Try_streamlit_app_v1_Signin.py · Try_streamlit_app_v2.py
Base: v2 (latest). Ported from v1_Signin: theme_choice session key, resolve_theme.
Auth: delegated to auth.py (Google OAuth + local fallback).
"""

# 0. Imports
import datetime
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

try:
    import user_store
    import notifications_store
except ImportError:
    user_store = None
    notifications_store = None

try:
    import email_helper
except ImportError:
    email_helper = None

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import torch
from huggingface_hub import hf_hub_download
from PIL import Image

# 1. Page config (MUST be first Streamlit call)
st.set_page_config(
    page_title="MindGuard - Suicidal Ideation Detector",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="auto",
)

# Module-level set — tracks which emails already accepted terms this server session.
# Survives logout/re-login so the user isn't asked twice in the same browser session.
_terms_consented_emails: set = set()

# 2. Constants & configuration
PRIMARY_COLOR = "#0F766E"
PRIMARY_COLOR_HOVER = "#115E59"
PRIMARY_TEXT = "#FFFFFF"

MINDGUARD_LOGO_URI = ""

SAMPLE_TWEETS = {
    "Positive": "Just got promoted at work! Feeling blessed and grateful for this opportunity.",
    "Negative": "I feel like nobody cares anymore. I am so depressed. What's the point of trying?",
}

STOPWORDS = {
    "a","about","above","after","again","all","am","an","and","any","are","as",
    "at","be","because","been","before","being","below","between","both","but",
    "by","cannot","could","did","do","does","doing","don't","down","during",
    "each","few","for","from","get","got","had","has","have","having","he",
    "her","here","hers","herself","him","himself","his","how","i","if","in",
    "into","is","it","its","itself","me","more","most","my","myself","no",
    "nor","not","of","off","on","once","only","or","other","our","out","over",
    "own","same","she","should","so","some","such","than","that","the","their",
    "theirs","them","then","there","these","they","this","those","through","to",
    "too","under","until","up","very","was","we","were","what","when","where",
    "which","while","who","whom","why","will","with","you","your","yours",
}

SOCIOECONOMIC_KEYWORDS = {
    "Employment": [
        "unemployed","fired","jobless","redundant","laid off","no income",
        "lost my job","lost the job","quit my job","cant find work",
        "rejected from","job rejection","no work","out of work",
        "terminated","resignation","job hunting","no job","between jobs",
        "struggling to find work","cant get hired","application rejected",
    ],
    "Housing": [
        "evicted","homeless","eviction","foreclosure","repossessed",
        "cant pay rent","behind on rent","losing my house","lost my home",
        "no place to live","sleeping rough","couch surfing","shelter",
        "kicked out","thrown out","living on the street","no roof",
        "cant afford rent","about to lose my home","housing crisis",
    ],
    "Financial": [
        "broke","debt","bankrupt","bankruptcy","no money","penniless",
        "cant afford","struggling financially","poverty","poor","destitute",
        "bills","overdue","repossession","bailiff","loan shark","in debt",
        "maxed out","credit card debt","financial crisis","cant make ends meet",
        "running out of money","nothing in my account","overdraft",
    ],
    "Relationships": [
        "divorce","divorced","breakup","broke up","separated","cheated on",
        "alone","abandoned","nobody cares","no one cares","nobody loves me",
        "lost my partner","widowed","widower","grief","bereaved","heartbroken",
        "relationship ended","left me","walked out","abusive relationship",
        "domestic violence","isolation","no friends","lost everyone",
        "nobody understands","feel invisible","completely alone",
    ],
    "Health": [
        "chronic pain","terminal","cancer","diagnosis","incurable","disabled",
        "mental illness","depression","anxiety","bipolar","schizophrenia",
        "addiction","addicted","alcoholic","alcohol abuse","drug abuse",
        "overdose","hospitalized","hospital","surgery","treatment failed",
        "no health insurance","cant afford medication","sick","illness",
        "eating disorder","self harm","self-harm","cutting","suicidal thoughts",
    ],
    "Social & Education": [
        "bullied","bullying","expelled","suspended","failed my exams",
        "dropped out","academic failure","social outcast","no friends",
        "excluded","isolated","discriminated","racism","harassment",
        "abused","victim","trauma","ptsd","refugee","asylum seeker",
    ],
}

RESOURCES = {
    "Kenya": [
        {"name": "Befrienders Kenya", "contact": "+254 722 178 177", "type": "Crisis line"},
        {"name": "Kenya Red Cross", "contact": "1199", "type": "Emergency"},
        {"name": "Chiromo Hospital Group", "contact": "+254 20 4291000", "type": "Mental health"},
        {"name": "Mathare Hospital MH Unit", "contact": "+254 20 2012185", "type": "Hospital"},
    ],
    "USA (National)": [
        {"name": "988 Suicide & Crisis Lifeline", "contact": "Call/text 988", "type": "Crisis line"},
        {"name": "Crisis Text Line", "contact": "Text HOME to 741741", "type": "Text-based"},
        {"name": "NAMI Helpline", "contact": "1-800-950-6264", "type": "Mental health"},
        {"name": "SAMHSA Helpline", "contact": "1-800-662-4357", "type": "Substance abuse & mental health"},
        {"name": "Veterans Crisis Line", "contact": "Call 988, press 1", "type": "Veterans"},
        {"name": "Trevor Project (LGBTQ+ youth)", "contact": "1-866-488-7386", "type": "Youth crisis"},
    ],
    "UK": [
        {"name": "Samaritans", "contact": "116 123", "type": "Crisis line"},
        {"name": "PAPYRUS (under 35s)", "contact": "0800 068 4141", "type": "Youth crisis"},
        {"name": "MIND", "contact": "0300 123 3393", "type": "Mental health"},
        {"name": "Shout", "contact": "Text SHOUT to 85258", "type": "Text-based"},
    ],
    "Australia": [
        {"name": "Lifeline", "contact": "13 11 14", "type": "Crisis line"},
        {"name": "Beyond Blue", "contact": "1300 22 4636", "type": "Mental health"},
        {"name": "Kids Helpline", "contact": "1800 55 1800", "type": "Youth (5-25)"},
    ],
    "Canada": [
        {"name": "Talk Suicide Canada", "contact": "1-833-456-4566", "type": "Crisis line"},
        {"name": "Crisis Text Line CA", "contact": "Text HOME to 686868", "type": "Text-based"},
        {"name": "Kids Help Phone", "contact": "1-800-668-6868", "type": "Youth"},
    ],
    "International": [
        {"name": "Find A Helpline", "contact": "findahelpline.com", "type": "Global directory"},
        {"name": "IASP", "contact": "https://www.iasp.info/resources/Crisis_Centres/", "type": "Global directory"},
        {"name": "Befrienders Worldwide", "contact": "https://www.befrienders.org", "type": "Global directory"},
    ],
}

TEAM_MEMBERS = [
    {
        "name": "Diana Opiyo",
        "role": "Lead Developer & ML Architect",
        "bio": "Leads the MindGuard research workflow, model comparison, training pipeline, and deployment readiness for mental health risk screening.",
        "image": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=900&q=80",
        "linkedin": "https://www.linkedin.com/in/diana-opiyo/",
    },
    {
        "name": "Andrew Njiyo",
        "role": "Technical Lead",
        "bio": "Guides risk-tier language, crisis-resource framing, and responsible use so model output stays grounded in human support.",
        "image": "https://images.unsplash.com/photo-1551836022-d5d88e9218df?auto=format&fit=crop&w=900&q=80",
        "linkedin": "https://www.linkedin.com/in/andrew-njiyo/",
    },
    {
        "name": "Dr. Suhila Sawesi",
        "role": "Health Informatics Advisor",
        "bio": "Reviews dataset consistency, checks label quality, and tracks model performance across text, platform exports, and OCR inputs.",
        "image": "https://images.unsplash.com/photo-1508214751196-bcfd4ca60f91?auto=format&fit=crop&w=900&q=80",
        "linkedin": "https://www.linkedin.com/in/suhila-sawesi/",
    },
    {
        "name": "Bushra Rashrash",
        "role": "Bioinformatics Specialist",
        "bio": "Turns model workflows into practical analysis tools with accessible layouts, clearer actions, and safer reporting touchpoints.",
        "image": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=900&q=80",
        "linkedin": "https://www.linkedin.com/in/bushra-rashrash/",
    },
]

US_STATE_RESOURCES = {
    "Alabama":        [{"name":"Alabama Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"AltaPointe Health","contact":"1-800-530-3727","type":"Mental health"}],
    "Alaska":         [{"name":"Careline Crisis Intervention","contact":"1-877-266-4357","type":"Crisis line"},{"name":"Alaska Mental Health Trust","contact":"907-274-7428","type":"Mental health"}],
    "Arizona":        [{"name":"AZ Crisis Line","contact":"1-800-631-1314","type":"Crisis line"},{"name":"Crisis Response Network","contact":"602-222-9444","type":"Crisis line"}],
    "Arkansas":       [{"name":"AR Crisis Line","contact":"1-888-274-7472","type":"Crisis line"},{"name":"UAMS Psychiatric Research","contact":"501-526-8100","type":"Mental health"}],
    "California":     [{"name":"CA Suicide Prevention Hotline","contact":"1-800-784-2433","type":"Crisis line"},{"name":"Didi Hirsch Mental Health","contact":"800-854-7771","type":"Crisis line"}],
    "Colorado":       [{"name":"CO Crisis Services","contact":"1-844-493-8255","type":"Crisis line"},{"name":"Mental Health Center of Denver","contact":"303-504-6500","type":"Mental health"}],
    "Connecticut":    [{"name":"CT Behavioral Health","contact":"1-800-467-3135","type":"Crisis line"},{"name":"DMHAS Crisis Line","contact":"211","type":"Crisis line"}],
    "Delaware":       [{"name":"DE Crisis Hotline","contact":"1-800-652-2929","type":"Crisis line"},{"name":"Connections Community Support","contact":"302-656-8308","type":"Mental health"}],
    "Florida":        [{"name":"FL Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"Crisis Center of Tampa Bay","contact":"813-234-1234","type":"Crisis line"}],
    "Georgia":        [{"name":"GA Crisis & Access Line","contact":"1-800-715-4225","type":"Crisis line"},{"name":"Behavioral Health Link","contact":"800-715-4225","type":"Crisis line"}],
    "Hawaii":         [{"name":"HI Crisis Line","contact":"1-800-753-6879","type":"Crisis line"},{"name":"AMHD Crisis Line","contact":"808-832-3100","type":"Mental health"}],
    "Idaho":          [{"name":"ID Careline","contact":"211","type":"Crisis line"},{"name":"Optum Idaho","contact":"1-855-202-0973","type":"Mental health"}],
    "Illinois":       [{"name":"IL Crisis Line","contact":"1-800-345-9049","type":"Crisis line"},{"name":"NAMI Illinois","contact":"1-800-826-4890","type":"Mental health"}],
    "Indiana":        [{"name":"IN Crisis Line","contact":"1-800-662-3445","type":"Crisis line"},{"name":"LifeLine Indiana","contact":"1-800-273-8255","type":"Crisis line"}],
    "Iowa":           [{"name":"IA Warm Line","contact":"1-800-777-3957","type":"Crisis line"},{"name":"MHDS Crisis Line","contact":"1-855-581-8111","type":"Crisis line"}],
    "Kansas":         [{"name":"KS Crisis Line","contact":"1-888-363-2287","type":"Crisis line"},{"name":"COMCARE Crisis","contact":"316-660-7500","type":"Crisis line"}],
    "Kentucky":       [{"name":"KY Crisis Line","contact":"1-800-221-0446","type":"Crisis line"},{"name":"Communicare","contact":"270-769-1304","type":"Mental health"}],
    "Louisiana":      [{"name":"LA Crisis Line","contact":"1-800-259-0570","type":"Crisis line"},{"name":"NAMI Louisiana","contact":"504-835-7633","type":"Mental health"}],
    "Maine":          [{"name":"ME Crisis Line","contact":"1-888-568-1112","type":"Crisis line"},{"name":"NAMI Maine","contact":"1-800-464-5767","type":"Mental health"}],
    "Maryland":       [{"name":"MD Crisis Hotline","contact":"1-800-422-0009","type":"Crisis line"},{"name":"Crisis Link","contact":"703-527-4077","type":"Crisis line"}],
    "Massachusetts":  [{"name":"MA Samaritans","contact":"1-877-870-4673","type":"Crisis line"},{"name":"NAMI Massachusetts","contact":"800-370-9085","type":"Mental health"}],
    "Michigan":       [{"name":"MI Crisis Text Line","contact":"Text HOME to 741741","type":"Text-based"},{"name":"NAMI Michigan","contact":"517-485-4049","type":"Mental health"}],
    "Minnesota":      [{"name":"MN Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"Canvas Health Crisis","contact":"651-777-5222","type":"Crisis line"}],
    "Mississippi":    [{"name":"MS Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"NAMI Mississippi","contact":"601-899-9227","type":"Mental health"}],
    "Missouri":       [{"name":"MO Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"Places for People","contact":"314-622-4600","type":"Mental health"}],
    "Montana":        [{"name":"MT Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"AWARE Inc","contact":"406-443-1010","type":"Mental health"}],
    "Nebraska":       [{"name":"NE Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"Heartland Family Service","contact":"402-553-3000","type":"Mental health"}],
    "Nevada":         [{"name":"NV Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"Crisis Support Services of NV","contact":"775-784-8090","type":"Crisis line"}],
    "New Hampshire":  [{"name":"NH Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"NAMI New Hampshire","contact":"1-800-242-6264","type":"Mental health"}],
    "New Jersey":     [{"name":"NJ Hopeline","contact":"1-855-654-6735","type":"Crisis line"},{"name":"NJ Mental Health Cares","contact":"1-866-202-4357","type":"Mental health"}],
    "New Mexico":     [{"name":"NM Crisis Line","contact":"1-855-662-7474","type":"Crisis line"},{"name":"NAMI New Mexico","contact":"505-260-0154","type":"Mental health"}],
    "New York":       [{"name":"NY OMH Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"NYC Well","contact":"1-888-692-9355","type":"Crisis line"},{"name":"NAMI NYC","contact":"212-684-3264","type":"Mental health"}],
    "North Carolina": [{"name":"NC Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"Trillium Health Resources","contact":"1-877-685-2415","type":"Mental health"}],
    "North Dakota":   [{"name":"ND Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"FirstStep Recovery","contact":"701-255-3692","type":"Mental health"}],
    "Ohio":           [{"name":"OH Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"Crisis Intervention Center","contact":"614-276-2273","type":"Crisis line"}],
    "Oklahoma":       [{"name":"OK Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"NAMI Oklahoma","contact":"405-230-1900","type":"Mental health"}],
    "Oregon":         [{"name":"OR Lines for Life","contact":"1-800-273-8255","type":"Crisis line"},{"name":"Oregon Crisis Network","contact":"503-652-4100","type":"Crisis line"}],
    "Pennsylvania":   [{"name":"PA Crisis Line","contact":"1-855-284-2494","type":"Crisis line"},{"name":"NAMI Pennsylvania","contact":"1-800-223-0500","type":"Mental health"}],
    "Rhode Island":   [{"name":"RI Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"Gateway Healthcare","contact":"401-724-8400","type":"Mental health"}],
    "South Carolina": [{"name":"SC Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"NAMI South Carolina","contact":"803-733-9592","type":"Mental health"}],
    "South Dakota":   [{"name":"SD Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"Volunteers of America Dakotas","contact":"605-339-1783","type":"Mental health"}],
    "Tennessee":      [{"name":"TN Crisis Line","contact":"1-855-274-7471","type":"Crisis line"},{"name":"NAMI Tennessee","contact":"615-361-6608","type":"Mental health"}],
    "Texas":          [{"name":"TX Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"Texas 211","contact":"211","type":"Local resources"},{"name":"NAMI Texas","contact":"512-693-2000","type":"Mental health"}],
    "Utah":           [{"name":"UT Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"Utah Crisis Services","contact":"801-587-3000","type":"Crisis line"}],
    "Vermont":        [{"name":"VT Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"Howard Center","contact":"802-488-6000","type":"Mental health"}],
    "Virginia":       [{"name":"VA Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"NAMI Virginia","contact":"888-486-8264","type":"Mental health"}],
    "Washington":     [{"name":"WA Crisis Line","contact":"1-866-427-4747","type":"Crisis line"},{"name":"Crisis Connections","contact":"866-427-4747","type":"Crisis line"}],
    "West Virginia":  [{"name":"WV Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"NAMI West Virginia","contact":"304-342-0497","type":"Mental health"}],
    "Wisconsin":      [{"name":"WI Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"Journey Mental Health","contact":"608-280-2600","type":"Mental health"}],
    "Wyoming":        [{"name":"WY Crisis Line","contact":"1-800-273-8255","type":"Crisis line"},{"name":"NAMI Wyoming","contact":"307-432-0837","type":"Mental health"}],
    "Washington D.C.":[{"name":"DC Crisis Line","contact":"1-888-793-4357","type":"Crisis line"},{"name":"DBH Access Helpline","contact":"888-793-4357","type":"Mental health"}],
}

THREE_MONTHS_AGO = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)
SIX_MONTHS_AGO  = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=182)

# 3. CSS / theme styles
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
#MainMenu, footer, header { visibility: hidden; }
.stAlert { border-radius:8px !important; }
[data-testid="stHeader"]       { display: none !important; height: 0 !important; }
[data-testid="stToolbar"]      { display: none !important; }
[data-testid="stDecoration"]   { display: none !important; }
[data-testid="stStatusWidget"] { display: none !important; }
html, body { margin: 0; padding: 0; }
[data-testid="stAppViewContainer"] { padding-top: 0 !important; }
:root {
    --ink: #111827;
    --body: #4b5563;
    --muted: #6b7280;
    --soft: #f5f7f6;
    --panel: #ffffff;
    --panel-strong: #f8faf9;
    --line: #d9e3df;
    --line-strong: #b7cbc4;
    --teal: #1D9E75;
    --teal-deep: #0F6E56;
    --teal-hover: #0B5E49;
    --red: #dc2626;
    --amber: #b45309;
    --green: #15803d;
    --shadow: 0 14px 34px rgba(15, 23, 42, 0.08);
}
.stApp {
    background:#f5f7f6 !important;
    font-family: 'Inter', sans-serif;
    color: var(--ink);
}
.main .block-container { max-width:100% !important; padding:0.65rem 0.9rem 0.65rem !important; margin:0 !important; }
[data-testid="stTabs"] [role="tablist"] { background:#ffffff !important; border-radius:8px; padding:4px; gap:4px; border:1px solid var(--line); flex-wrap:wrap; box-shadow:var(--shadow); margin-top:0.15rem; }
[data-testid="stTabs"] button[role="tab"] { color:var(--body) !important; border-radius:8px !important; font-size:0.76rem !important; font-weight:700 !important; padding:6px 11px !important; border:none !important; transition:all 0.2s; }
[data-testid="stTabs"] button[role="tab"] * { color:var(--body) !important; }
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] { background:var(--teal-deep) !important; color:#ffffff !important; box-shadow:0 5px 12px rgba(15,110,86,0.18); }
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] * { color:#ffffff !important; }
[data-testid="stTabs"] button[role="tab"]:hover { color:var(--teal-deep) !important; background:#eaf7f2 !important; }
[data-testid="stTabs"] button[role="tab"]:hover * { color:var(--teal-deep) !important; }
h1,h2,h3,h4 { color:var(--ink) !important; font-weight:700 !important; }
h2 { font-size:1.15rem !important; margin:0 0 0.35rem !important; }
h3 { font-size:0.95rem !important; margin:0.35rem 0 0.25rem !important; }
p,li { color:var(--body) !important; font-size:0.80rem; line-height:1.55; margin:0.05rem 0; }
strong { color:var(--ink) !important; font-weight:600 !important; }
a { color:var(--teal-deep) !important; }
.app-shell { display:flex; justify-content:space-between; align-items:center; gap:0.75rem; background:#ffffff; border:1px solid var(--line); border-radius:8px; padding:0.48rem 0.62rem; margin-bottom:0.15rem; box-shadow:var(--shadow); min-height:54px; }
.app-header { display:flex; align-items:center; gap:0.55rem; margin-bottom:0; min-width:0; }
.app-logo { display:flex; align-items:center; justify-content:center; width:132px; height:38px; border-radius:8px; background:#ffffff; border:1px solid var(--line); padding:0.25rem 0.45rem; overflow:hidden; flex:0 0 auto; }
.app-logo img { display:block; width:100%; height:100%; object-fit:contain; }
.app-header-title { font-size:1.08rem; font-weight:800; color:var(--ink); line-height:1.1; }
.app-subtitle { font-size:0.72rem; color:var(--body); margin-top:0.05rem; }
.signed-in-chip { display:inline-flex; align-items:center; gap:0.35rem; border:1px solid var(--line); border-radius:8px; padding:0.34rem 0.55rem; color:var(--body); background:#f8faf9; font-size:0.72rem; font-weight:700; white-space:nowrap; }
.divider { border:none; border-top:1px solid var(--line); margin:0.55rem 0; }
.section-label { font-size:0.72rem; font-weight:800; color:var(--teal-deep); letter-spacing:0; text-transform:uppercase; margin:0.65rem 0 0.3rem; }
.stTextArea label, .stTextInput label, [data-testid="stSelectbox"] label, [data-testid="stFileUploader"] label { color:var(--ink) !important; font-weight:600 !important; font-size:0.78rem !important; }
.stTextArea textarea, .stTextInput input { background:#ffffff !important; color:var(--ink) !important; border:1.5px solid #cfd8d4 !important; border-radius:8px !important; font-size:0.82rem !important; padding:0.65rem 0.75rem !important; caret-color:var(--teal-deep) !important; }
textarea, input[type="text"], input[type="password"] { color:var(--ink) !important; -webkit-text-fill-color:var(--ink) !important; }
input:-webkit-autofill, input:-webkit-autofill:hover, input:-webkit-autofill:focus, textarea:-webkit-autofill { -webkit-text-fill-color:var(--ink) !important; -webkit-box-shadow:0 0 0px 1000px #ffffff inset !important; transition:background-color 5000s ease-in-out 0s; }
.stTextArea textarea:focus, .stTextInput input:focus { border-color:var(--teal) !important; box-shadow:0 0 0 3px rgba(29,158,117,0.16) !important; outline:none !important; }
.stTextArea textarea::placeholder, .stTextInput input::placeholder { color:#9ca3af !important; font-style:normal; opacity:1 !important; }
.stTextArea textarea:focus::placeholder, .stTextInput input:focus::placeholder { color:transparent !important; opacity:0 !important; }
[data-testid="stFileUploader"] section { background:#ffffff !important; border:1.5px dashed #cfd8d4 !important; border-radius:8px !important; padding:0.65rem !important; }
[data-testid="stFileUploader"] section p { font-size:0.72rem !important; color:var(--body) !important; }
.stButton > button, .stFormSubmitButton > button, [data-testid="stFormSubmitButton"] button { background:var(--teal-deep) !important; color:#ffffff !important; font-weight:800 !important; padding:0 1rem !important; border-radius:8px !important; border:none !important; font-size:0.78rem !important; box-shadow:0 8px 18px rgba(15,110,86,0.22) !important; transition:all 0.25s ease !important; width:100%; height:38px; }
.stButton > button *, .stFormSubmitButton > button *, [data-testid="stFormSubmitButton"] button * { color:#ffffff !important; }
.stButton > button:hover, .stFormSubmitButton > button:hover, [data-testid="stFormSubmitButton"] button:hover { background:var(--teal-hover) !important; transform:translateY(-1px) !important; color:#ffffff !important; }
.stButton > button:disabled, .stFormSubmitButton > button:disabled, [data-testid="stFormSubmitButton"] button:disabled { background:#d7e1dd !important; color:#64748b !important; box-shadow:none !important; }
[data-testid="stDownloadButton"] > button { background:#ffffff !important; color:var(--ink) !important; border:1px solid var(--line) !important; border-radius:8px !important; font-size:0.74rem !important; height:34px; padding:0 0.8rem !important; }
.result-card { background:var(--panel); border-radius:8px; padding:0.75rem 0.85rem; margin:0.35rem 0; border:1px solid var(--line); animation:slideUp 0.35s ease-out; box-shadow:var(--shadow); }
@keyframes slideUp { from{opacity:0;transform:translateY(12px)} to{opacity:1;transform:translateY(0)} }
.post-card { background:#ffffff; border-radius:8px; padding:0.55rem 0.7rem; margin:0.28rem 0; border:1px solid var(--line); border-left:4px solid var(--teal-deep); font-size:0.74rem; box-shadow:0 8px 22px rgba(15,23,42,0.05); }
.post-card.high   { border-left-color:var(--red); }
.post-card.medium { border-left-color:var(--amber); }
.post-card.low    { border-left-color:var(--green); }
.resource-card { background:#ffffff; border-radius:8px; padding:0.5rem 0.65rem; margin:0.24rem 0; border:1px solid var(--line); border-left:4px solid var(--teal-deep); font-size:0.74rem; box-shadow:0 8px 22px rgba(15,23,42,0.05); }
.resource-name { font-weight:800; font-size:0.82rem; margin-bottom:0.05rem; color:var(--ink) !important; }
.resource-type { font-size:0.68rem; margin:1px 0 0.1rem; color:var(--muted) !important; }
.resource-contact, .resource-contact a, .resource-contact span { font-weight:700; font-size:0.78rem; text-decoration:underline; color:var(--teal-deep) !important; }
.resource-contact span { text-decoration:none; }
.socio-tag { display:inline-block; background:#eaf7f2; color:var(--teal-deep); border-radius:6px; padding:2px 8px; margin:2px; font-size:0.7rem; border:1px solid #c9ebe0; }
.platform-badge { display:inline-block; background:#ffffff; border:1px solid var(--line); border-radius:8px; padding:0.25rem 0.55rem; font-size:0.7rem; margin-bottom:0.25rem; color:var(--body); }
.stat-row { display:flex; gap:0.28rem; margin-bottom:0.28rem; }
.stat-card { flex:1; background:#ffffff; border-radius:8px; padding:0.45rem 0.28rem; text-align:center; border:1px solid var(--line); box-shadow:0 8px 22px rgba(15,23,42,0.05); }
.stat-number { font-size:1.15rem; font-weight:800; color:var(--teal-deep); }
.stat-label  { font-size:0.58rem; color:var(--muted); text-transform:uppercase; letter-spacing:0; }
.conf-badge { display:inline-block; padding:0.22rem 0.55rem; border-radius:8px; font-size:0.72rem; font-weight:700; }
.conf-high   { background:#dcfce7; color:#14532d; }
.conf-medium { background:#fef3c7; color:#92400e; }
.conf-low    { background:#eaf7f2; color:var(--teal-deep); }
.risk-high { color:var(--red) !important; font-weight:700 !important; }
.risk-low  { color:var(--green) !important; font-weight:700 !important; }
.stProgress > div > div > div > div { background:var(--teal-deep); border-radius:6px; height:7px; }
.stProgress > div > div { background:#e5e7eb; border-radius:6px; }
.stWarning { background:#fffbeb !important; color:#92400e !important; border-left:3px solid #f59e0b !important; border-radius:8px !important; padding:0.45rem 0.65rem !important; font-size:0.74rem; }
.stInfo    { background:#ecfdf5 !important; color:#065f46 !important; border-left:3px solid var(--teal) !important; border-radius:8px !important; padding:0.45rem 0.65rem !important; font-size:0.74rem; }
.stError   { background:#fef2f2 !important; color:#991b1b !important; border-left:3px solid var(--red) !important; border-radius:8px !important; padding:0.45rem 0.65rem !important; font-size:0.74rem; font-weight:600; }
.stSuccess { background:#f0fdf4 !important; color:#166534 !important; border-left:3px solid var(--green) !important; border-radius:8px !important; padding:0.45rem 0.65rem !important; font-size:0.74rem; }
.support-pill { background:#ffffff; border-radius:8px; padding:0.42rem 0.5rem; margin:0.1rem 0; border:1px solid var(--line); font-size:0.7rem; line-height:1.7; text-align:center; color:var(--body) !important; }
.support-pill strong { display:block; margin-bottom:0.08rem; color:var(--teal-deep) !important; font-size:0.72rem; }
.support-pill a { color:var(--teal-deep) !important; }
.remember-card { background:#ffffff; border-radius:8px; padding:0.45rem 0.6rem; border:1px solid var(--line); font-size:0.72rem; text-align:center; margin-top:0.32rem; color:var(--body) !important; }
.remember-card strong { color:var(--teal-deep) !important; }
.col-footer { font-size:0.66rem; color:var(--muted); text-align:center; border-top:1px solid var(--line); padding-top:0.35rem; margin-top:0.55rem; }
.unified-card { background:#ffffff; border-radius:8px; padding:0.65rem 0.8rem; margin:0.35rem 0; border:1px solid var(--line); box-shadow:var(--shadow); }
[data-testid="stSelectbox"] div[data-baseweb="select"] > div { background:#ffffff !important; color:var(--ink) !important; border:1.5px solid #cfd8d4 !important; border-radius:8px !important; }
[data-testid="stSelectbox"] div[data-baseweb="select"]:focus-within > div { border-color:var(--teal) !important; box-shadow:0 0 0 3px rgba(29,158,117,0.16) !important; }
[data-testid="stSelectbox"] div[data-baseweb="select"] span { color:var(--ink) !important; }
[data-baseweb="popover"], [data-baseweb="menu"] { background:#ffffff !important; border:1px solid var(--line) !important; border-radius:8px !important; box-shadow:var(--shadow) !important; }
[data-baseweb="popover"] ul li { color:var(--ink) !important; background:#ffffff !important; font-size:0.8rem !important; }
[data-baseweb="popover"] ul li:hover { background:#eaf7f2 !important; color:var(--teal-deep) !important; }
[data-baseweb="popover"] ul li[aria-selected="true"] { background:var(--teal-deep) !important; color:#ffffff !important; }
[data-baseweb="option"] { color:var(--ink) !important; background:#ffffff !important; }
[data-baseweb="option"]:hover { background:#eaf7f2 !important; }
[data-testid="stExpander"] { background:#ffffff !important; border:1px solid var(--line) !important; border-radius:8px !important; box-shadow:none !important; }
[data-testid="stExpander"] details, [data-testid="stExpander"] summary { background:#ffffff !important; color:var(--ink) !important; border-color:var(--line) !important; }
[data-testid="stExpander"] summary *, [data-testid="stExpander"] details * { color:var(--ink) !important; }
.auth-copy { padding:3.35rem 3.05rem 2.45rem; border-radius:8px 0 0 8px; background:#064b3b; border:1px solid #064b3b; min-height:520px; height:min(560px, calc(100vh - 72px)); display:flex; flex-direction:column; justify-content:space-between; box-sizing:border-box; }
.auth-brand { display:flex; align-items:center; margin-bottom:2.75rem; }
.auth-brand-logo { display:flex; align-items:center; justify-content:center; width:188px; height:58px; border-radius:8px; background:#ffffff; padding:0.45rem 0.7rem; overflow:hidden; }
.auth-kicker { color:#a7d8cb; font-size:0.76rem; text-transform:uppercase; font-weight:800; margin-bottom:1.35rem; }
.auth-title { color:#f8faf9; font-size:2.15rem; line-height:1.16; font-weight:800; margin-bottom:1.55rem; max-width:360px; }
.auth-text { color:#e8fff7 !important; font-size:0.95rem; line-height:1.6; max-width:360px; }
.trust-row { display:flex; flex-direction:column; align-items:flex-start; gap:0.72rem; margin-top:2.5rem; }
.trust-pill { display:inline-flex; align-items:center; gap:0.62rem; border:none; border-radius:0; background:transparent; color:#d9eee8; padding:0; font-size:0.88rem; font-weight:700; }
.trust-pill::before { content:""; width:8px; height:8px; border-radius:999px; background:#75cdb4; flex:0 0 auto; }
.signin-heading h2 { color:var(--ink) !important; font-size:1.7rem !important; line-height:1.1 !important; margin:0 0 0.5rem !important; }
.signin-heading p { color:var(--ink) !important; font-size:0.95rem !important; line-height:1.2 !important; max-width:300px; margin:0 0 1.8rem !important; }
.team-hero { display:flex; justify-content:space-between; align-items:flex-end; gap:1rem; border:1px solid var(--line); background:#ffffff; border-radius:8px; padding:0.85rem 1rem; margin-bottom:0.7rem; box-shadow:var(--shadow); }
.team-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:0.7rem; }
.team-card { background:#ffffff; border:1px solid var(--line); border-radius:8px; overflow:hidden; box-shadow:var(--shadow); }
.team-card img { width:100%; height:210px; object-fit:cover; display:block; }
.team-card-body { padding:0.72rem; }
.team-name { font-size:0.95rem; font-weight:800; color:var(--ink); margin-bottom:0.08rem; }
.team-role { font-size:0.72rem; color:var(--teal-deep); font-weight:800; text-transform:uppercase; margin-bottom:0.35rem; }
.team-bio { font-size:0.76rem; line-height:1.55; color:var(--body); min-height:72px; }
.team-link { display:inline-block; margin-top:0.5rem; padding:0.34rem 0.55rem; border-radius:8px; background:#eaf7f2; color:var(--teal-deep) !important; text-decoration:none; font-weight:800; font-size:0.72rem; }
.terms-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:0.45rem; margin:0.55rem 0; }
.terms-clause { border:1px solid var(--line); border-radius:8px; padding:0.55rem 0.65rem; background:#f8faf9; }
.terms-clause strong { display:block; margin-bottom:0.16rem; font-size:0.78rem; color:var(--ink) !important; }
.terms-clause span { font-size:0.74rem; line-height:1.45; color:var(--body) !important; }
.terms-alert { border:1px solid #fde68a; border-radius:8px; padding:0.55rem 0.65rem; background:#fffbeb; margin:0.45rem 0; color:#92400e; }
@media (max-width: 980px) {
    .team-grid, .terms-grid { grid-template-columns:1fr 1fr; }
    .auth-copy { min-height:auto; }
    .app-shell { align-items:flex-start; flex-direction:column; }
}
@media (max-width: 620px) {
    .main .block-container { padding:0.7rem !important; }
    .auth-title { font-size:1.7rem; }
    .team-grid, .terms-grid { grid-template-columns:1fr; }
    .team-card img { height:230px; }
}

/* ── Sidebar ─────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid #d9e3df !important;
}
[data-testid="stSidebar"] > div:first-child {
    padding: 1.2rem 1rem 1.5rem !important;
}
[data-testid="stSidebar"] * {
    color: #111827 !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #111827 !important;
    font-size: 0.82rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.04em !important;
    text-transform: uppercase !important;
    margin: 0.8rem 0 0.4rem !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stCaption {
    color: #4b5563 !important;
    font-size: 0.78rem !important;
}
[data-testid="stSidebar"] .stButton > button {
    background: #f0fdf8 !important;
    color: #065f46 !important;
    border: 1px solid #a7f3d0 !important;
    border-radius: 6px !important;
    font-size: 0.74rem !important;
    font-weight: 600 !important;
    padding: 0.3rem 0.6rem !important;
    width: 100% !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: #d1fae5 !important;
    border-color: #6ee7b7 !important;
}
[data-testid="stSidebar"] .stExpander {
    border: 1px solid #d9e3df !important;
    border-radius: 8px !important;
    margin-bottom: 0.4rem !important;
    background: #f8faf9 !important;
}
[data-testid="stSidebar"] .stExpander summary {
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    color: #111827 !important;
}
[data-testid="stSidebar"] code,
[data-testid="stSidebar"] pre {
    background: #f1f5f9 !important;
    color: #0f766e !important;
    font-size: 0.72rem !important;
    border-radius: 6px !important;
    word-break: break-all !important;
}
[data-testid="stSidebar"] hr {
    border-color: #d9e3df !important;
    margin: 0.6rem 0 !important;
}
[data-testid="stSidebar"] .stAlert {
    font-size: 0.76rem !important;
}
/* Sidebar toggle button visibility */
[data-testid="stSidebarCollapsedControl"] button {
    background: #ffffff !important;
    border: 1px solid #d9e3df !important;
    color: #0f766e !important;
}
</style>
""", unsafe_allow_html=True)

# 3b. MindGuard UI overhaul CSS — injected only inside main_app() (post-auth)
MG_UI_CSS = """
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@latest/dist/tabler-icons.min.css">
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap');

/* Hide default Streamlit collapse control so the sidebar feels pinned */
[data-testid="stSidebarCollapsedControl"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }

/* Override stApp background + font for authenticated app */
.stApp { background: #f7f9fb !important; font-family: 'DM Sans', 'Inter', system-ui, sans-serif !important; }

/* ── Dark sidebar — pinned, always visible ────────────────────── */
[data-testid="stSidebar"] {
    background: #080d12 !important;
    border-right: 1px solid #161d26 !important;
    min-width: 220px !important;
    max-width: 220px !important;
    width: 220px !important;
    padding: 0 !important;
}
[data-testid="stSidebar"] > div:first-child { padding: 0 !important; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0 !important; }
[data-testid="stSidebar"] * {
    color: #6b7280 !important;
    font-family: 'DM Sans', system-ui, sans-serif !important;
}

/* Sidebar nav buttons (Streamlit st.button overrides for sidebar) */
[data-testid="stSidebar"] .stButton { margin: 0 !important; padding: 0 !important; }
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    border: none !important;
    border-radius: 7px !important;
    padding: 7px 12px !important;
    margin: 1px 6px !important;
    width: calc(100% - 12px) !important;
    text-align: left !important;
    font-size: 0.76rem !important;
    font-weight: 500 !important;
    color: #6b7280 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    gap: 9px !important;
    transition: background 0.15s, color 0.15s !important;
    box-shadow: none !important;
    height: auto !important;
    min-height: 0 !important;
    line-height: 1.4 !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: #0e1520 !important;
    color: #d1d5db !important;
    transform: none !important;
}
[data-testid="stSidebar"] .stButton > button * { color: inherit !important; }
[data-testid="stSidebar"] .stButton > button p { color: inherit !important; margin: 0 !important; font-size: 0.76rem !important; }

/* Sidebar brand block */
.mg-sb-brand {
    display: flex; align-items: center; gap: 9px;
    padding: 15px 14px 12px; border-bottom: 1px solid #161d26;
}
.mg-sb-logo {
    width: 30px; height: 30px; border-radius: 8px;
    background: linear-gradient(135deg, #0F766E, #1D9E75);
    display: flex; align-items: center; justify-content: center;
    color: #fff !important; font-weight: 800; font-size: 0.7rem; flex-shrink: 0;
}
.mg-sb-name { color: #f3f4f6 !important; font-size: 0.88rem; font-weight: 700; letter-spacing: -0.02em; }
.mg-sb-section { color: #4b5563 !important; font-size: 0.58rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.12em; padding: 12px 14px 5px; }
.mg-sb-active {
    display: flex; align-items: center; gap: 9px;
    padding: 8px 12px 8px 10px; margin: 1px 6px;
    border-radius: 7px; font-size: 0.76rem;
    background: #0f2724; color: #e2f4f1 !important;
    font-weight: 600; border-left: 2px solid #1D9E75;
}
.mg-sb-active i { color: #34d399 !important; font-size: 15px; }
.mg-sb-footer {
    padding: 11px 14px; border-top: 1px solid #161d26;
    display: flex; align-items: center; gap: 9px;
    margin-top: 12px;
}
.mg-sb-avatar {
    width: 30px; height: 30px; border-radius: 50%;
    background: linear-gradient(135deg, #0F766E, #1D9E75);
    display: flex; align-items: center; justify-content: center;
    color: #fff !important; font-weight: 700; font-size: 0.72rem; flex-shrink: 0;
}
.mg-sb-uname { color: #f3f4f6 !important; font-size: 0.76rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mg-sb-uemail { color: #4b5563 !important; font-size: 0.64rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mg-sb-pill {
    background: rgba(15,118,110,0.15); color: #34d399 !important;
    border: 1px solid rgba(52,211,153,0.18); border-radius: 999px;
    padding: 2px 7px; font-size: 0.58rem; font-weight: 700;
    text-transform: uppercase; flex-shrink: 0;
}

/* ── Topbar ─────────────────────────────────────────────────────── */
.mg-topbar {
    height: 46px; background: rgba(255,255,255,0.97);
    border-bottom: 0.5px solid rgba(229,231,235,0.8);
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 20px; position: sticky; top: 0; z-index: 100;
    margin: 0 -0.9rem 14px;
}
.mg-topbar-title { font-size: 0.84rem; font-weight: 600; color: #1f2937; }
.mg-topbar-right { display: flex; align-items: center; gap: 12px; }
.mg-topbar-bell { position: relative; color: #6b7280; cursor: pointer; line-height: 1; }
.mg-topbar-bell i { font-size: 18px; }
.mg-bell-dot { position: absolute; top: -2px; right: -2px; width: 7px; height: 7px; background: #ef4444; border-radius: 50%; border: 1.5px solid #fff; }
.mg-topbar-av {
    width: 28px; height: 28px; border-radius: 50%;
    background: linear-gradient(135deg, #0F766E, #1D9E75);
    display: flex; align-items: center; justify-content: center;
    color: #fff !important; font-weight: 700; font-size: 0.65rem; cursor: pointer;
}

/* ── Panel cards (main content) ─────────────────────────────────── */
.mg-panel {
    background: #ffffff; border-radius: 12px;
    border: 0.5px solid rgba(229,231,235,0.8);
    padding: 16px 18px;
    box-shadow: 0 1px 4px rgba(15,23,42,0.04);
}
.mg-panel-title {
    font-size: 0.78rem; font-weight: 700; color: #1f2937;
    margin-bottom: 10px; padding-bottom: 8px;
    border-bottom: 1px solid #f1f5f9;
    display: flex; align-items: center; gap: 6px;
}
.mg-panel-title i { font-size: 15px; color: #0F766E; }

/* Risk gauge stats row */
.mg-risk-row { display: flex; gap: 8px; margin-top: 10px; }
.mg-risk-stat {
    flex: 1; background: #fafbfc; border-radius: 8px;
    border: 0.5px solid #f1f5f9; padding: 7px 8px; text-align: center;
}
.mg-risk-val { font-size: 0.85rem; font-weight: 700; color: #0F766E; }
.mg-risk-lbl { font-size: 0.58rem; color: #9ca3af; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 1px; }

/* Alert / safe boxes */
.mg-alert-box {
    margin-top: 8px; background: #fef2f2;
    border: 0.5px solid #fecaca; border-radius: 7px;
    padding: 7px 10px; font-size: 0.7rem; color: #991b1b;
    font-weight: 600; display: flex; align-items: center; gap: 6px;
}
.mg-alert-box i { font-size: 14px; }
.mg-safe-box {
    margin-top: 8px; background: #f0fdf4;
    border: 0.5px solid #bbf7d0; border-radius: 7px;
    padding: 7px 10px; font-size: 0.7rem; color: #166534;
    font-weight: 600; display: flex; align-items: center; gap: 6px;
}
.mg-safe-box i { font-size: 14px; }

/* Session analytics stat cards */
.mg-stat-row { display: grid; grid-template-columns: repeat(3,1fr); gap: 6px; margin-bottom: 10px; }
.mg-stat-card {
    background: #fff; border: 0.5px solid #f1f5f9;
    border-top: 2px solid #0F766E; border-radius: 8px;
    padding: 8px 6px; text-align: center;
}
.mg-stat-num { font-size: 1.3rem; font-weight: 800; color: #0F766E; letter-spacing: -0.02em; }
.mg-stat-lbl { font-size: 0.55rem; color: #9ca3af; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 2px; }

/* History rows */
.mg-history-row { display: flex; align-items: center; gap: 6px; padding: 4px 0; border-bottom: 0.5px solid #f9fafb; }
.mg-h-cls { font-size: 0.65rem; font-weight: 700; min-width: 80px; }
.mg-h-cls.risk { color: #dc2626; }
.mg-h-cls.safe { color: #0F6E56; }
.mg-h-ts { font-size: 0.6rem; color: #9ca3af; min-width: 38px; }
.mg-h-txt { font-size: 0.62rem; color: #6b7280; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; }

/* Mode toggle */
.mg-mode-wrap { display: flex; gap: 6px; margin-bottom: 10px; }
.mg-mode-btn {
    flex: 1; padding: 5px 0; border-radius: 7px;
    border: 0.5px solid #e5e7eb; background: #fafbfc;
    font-size: 0.7rem; font-weight: 600; color: #6b7280;
    text-align: center; cursor: pointer;
}
.mg-mode-btn.active { background: #0F766E; color: #fff !important; border-color: #0F766E; }

/* Platform strip cards (when in platform-detail sub-tabs) */
.mg-strip { background: #fff; border-radius: 12px; border: 0.5px solid rgba(229,231,235,0.7); overflow: hidden; }
.mg-strip-tabs { display: flex; background: #f8fafc; border-bottom: 0.5px solid #f1f5f9; padding: 0 14px; overflow-x: auto; }
.mg-strip-tab { padding: 10px 14px; font-size: 0.7rem; font-weight: 500; color: #94a3b8; white-space: nowrap; border-bottom: 2px solid transparent; cursor: pointer; }
.mg-strip-tab.active { color: #0F766E !important; border-bottom-color: #0F766E; font-weight: 600; }
</style>
"""

# 4. Session state defaults (all keys initialized here)
_defaults = {
    # Analytics
    "analytics":        {"total_analyses": 0, "positive_count": 0, "negative_count": 0, "history": []},
    # User input
    "user_input":       "",
    "should_analyze":   False,
    "last_result":      None,
    "input_mode":       "text",
    "download_text":    "",
    # Platform results
    "reddit_results":   None,
    "video_result":     None,
    "bluesky_results":  None,
    "mastodon_results": None,
    "youtube_results":  None,
    "file_results":     None,
    "unified_results":  None,
    "facebook_results": None,
    "twitter_results":  None,
    # Platform flags
    "bsky_run":         False,
    "bsky_target":      "",
    "bsky_min_run":     0.0,
    "bsky_n_run":       20,
    "bsky_pending":     None,
    "fb_pending":       None,
    "tw_pending":       None,
    "fb_triggered":     False,
    "tw_triggered":     False,
    # Auth  — preserve all keys; never rename
    "authenticated":    False,
    "auth_user":        "",
    "auth_role":        "Clinical review",
    "terms_accepted":   False,
    "terms_accepted_at": "",
    "theme_choice":     "Auto",   # ported from v1_Signin
    # Session timeout & role
    "last_activity":            datetime.datetime.now().isoformat(),
    "session_timeout_minutes":  30,
    "auth_name":                "",
    "auth_role_type":           "counselor",  # "student", "counselor", "admin"
    "notifications_unread":     0,
    "referral_code":            "",
    # Sidebar navigation
    "mg_page":                  "dashboard",
}
for _k, _v in _defaults.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

for _entry in st.session_state.analytics.get("history", []):
    for _field, _default in [("cls", "Unknown"), ("ts", ""), ("prob", 0.0), ("txt", "")]:
        _entry.setdefault(_field, _default)

# 4b-pre. Referral query-param capture (runs every page load, before auth gate)
_ref_code = st.query_params.get("ref", "")
if _ref_code and not st.session_state.get("incoming_ref"):
    st.session_state.incoming_ref = _ref_code

# 4b. Auth helpers

def reset_auth_state() -> None:
    st.session_state.authenticated = False
    st.session_state.auth_user = ""
    st.session_state.auth_name = ""
    st.session_state.auth_role = "Clinical review"
    st.session_state.auth_role_type = "counselor"
    st.session_state.terms_accepted = False
    st.session_state.terms_accepted_at = ""
    st.session_state.referral_code = ""
    st.session_state.notifications_unread = 0


def _auth_success(email: str, name: str, role: str = "Clinical review", role_type: str = "counselor", referral_code: str = "") -> None:
    """Mark session as authenticated and trigger rerun."""
    already_consented = email in _terms_consented_emails
    st.session_state.authenticated      = True
    st.session_state.auth_user          = email
    st.session_state.user_email         = email
    st.session_state.user_name          = name
    st.session_state.auth_name          = name
    st.session_state.auth_role          = role
    st.session_state.auth_role_type     = role_type
    st.session_state.referral_code      = referral_code
    st.session_state.terms_accepted     = already_consented
    st.session_state.terms_accepted_at  = (
        st.session_state.get("terms_accepted_at", "") if already_consented else ""
    )
    st.session_state.last_activity      = datetime.datetime.now().isoformat()
    st.session_state.pop("terms_consent_checkbox", None)
    st.rerun()


def render_sign_in() -> None:
    """
    Sign-in page with three auth methods:
      Tab 1 — Email & Password  (Supabase Auth — primary, supports Student/Counselor/Admin)
      Tab 2 — Google OAuth      (streamlit-google-auth — when credentials are configured)
      Tab 3 — Local Account     (streamlit-authenticator — admin/staff fallback)
    """
    st.markdown("""
    <style>
    html, body, .stApp { overflow-y: hidden !important; }
    .main .block-container {
        max-width: 1080px !important;
        padding: 2rem 1rem 0.5rem !important;
        margin: 0 auto !important;
    }
    [data-testid="stHorizontalBlock"] { gap: 0 !important; align-items: stretch !important; }
    [data-testid="stHorizontalBlock"] > div { padding: 0 !important; }
    [data-testid="stHorizontalBlock"] > div:last-child {
        background: #ffffff;
        border: 1px solid #d1d9d5;
        border-left: none;
        border-radius: 0 10px 10px 0;
    }
    [data-testid="stHorizontalBlock"] > div:last-child > div:first-child {
        padding: 2.4rem 3rem 2rem;
        min-height: 540px;
        box-sizing: border-box;
    }
    .mg-auth-unavailable {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
        padding: 2.5rem 1rem;
        color: #9ca3af;
        font-size: 0.82rem;
        text-align: center;
    }
    .mg-auth-unavailable svg { opacity: 0.35; }
    .mg-role-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.03em;
        text-transform: uppercase;
        margin-bottom: 0.5rem;
    }
    .mg-role-student  { background: #dbeafe; color: #1e40af; }
    .mg-role-counselor{ background: #d1fae5; color: #065f46; }
    .mg-role-admin    { background: #fef3c7; color: #92400e; }
    </style>
    """, unsafe_allow_html=True)

    left, right = st.columns([1, 1])

    with left:
        st.markdown("""
        <div class="auth-copy">
            <div>
                <div class="auth-brand">
                    <div class="auth-brand-logo">
                        <div style="font-size:22px;font-weight:700;color:#0D9488;letter-spacing:-0.5px;">
                            MindGuard AI
                        </div>
                    </div>
                </div>
                <div class="auth-kicker">SECURE WORKSPACE</div>
                <div class="auth-title">Review high-risk signals with care.</div>
                <p class="auth-text">
                    A consent-first clinical decision-support tool for trained mental health
                    professionals. Sign in to access the analysis workspace.
                </p>
            </div>
            <div class="trust-row">
                <div class="trust-pill">Consent-first</div>
                <div class="trust-pill">No data stored</div>
                <div class="trust-pill">Crisis resources included</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with right:
        st.markdown(
            '<div class="signin-heading"><h2>Sign in to MindGuard</h2>'
            '<p>Use your account or create one below.</p></div>',
            unsafe_allow_html=True,
        )

        tab_email, tab_google, tab_local = st.tabs([
            "Email & Password", "Google", "Local Account"
        ])

        # ── Tab 1: Supabase email/password (primary) ─────────────────────
        with tab_email:
            sub_signin, sub_register = st.tabs(["Sign In", "Create Account"])

            with sub_signin:
                with st.form("ep_signin_form"):
                    ep_email    = st.text_input("Email", placeholder="name@organization.org", key="ep_signin_email")
                    ep_password = st.text_input("Password", type="password", placeholder="Enter password", key="ep_signin_password")
                    ep_submit   = st.form_submit_button("Sign in", use_container_width=True)
                if ep_submit:
                    if not ep_email.strip() or not ep_password.strip():
                        st.warning("Enter an email and password to continue.")
                    elif user_store is None:
                        st.error("User store module not available.")
                    else:
                        _user = user_store.authenticate_user(ep_email.strip(), ep_password)
                        if _user:
                            _role_display = _user.get("role", "counselor").capitalize()
                            _auth_success(
                                email=_user["email"],
                                name=_user.get("name", _user["email"].split("@")[0]),
                                role=_role_display,
                                role_type=_user.get("role", "counselor"),
                                referral_code=_user.get("referral_code", ""),
                            )
                        else:
                            st.error("Invalid email or password.")

            with sub_register:
                with st.form("ep_register_form"):
                    reg_name     = st.text_input("Full Name", placeholder="Jane Doe", key="reg_name")
                    reg_email    = st.text_input("Email", placeholder="name@organization.org", key="reg_email")
                    reg_password = st.text_input("Password", type="password", placeholder="Create a password", key="reg_password")
                    reg_confirm  = st.text_input("Confirm Password", type="password", placeholder="Repeat password", key="reg_confirm")
                    reg_role     = st.selectbox("Role", ["Student", "Counselor"], key="reg_role")
                    # DOB — only for students
                    reg_dob = None
                    if reg_role == "Student":
                        reg_dob = st.date_input(
                            "Date of Birth",
                            value=None,
                            min_value=datetime.date(1940, 1, 1),
                            max_value=datetime.date.today(),
                            key="reg_dob",
                        )
                    # Parent email — only for students under 18
                    reg_parent_email = ""
                    if reg_role == "Student" and reg_dob is not None:
                        _today = datetime.date.today()
                        _age   = _today.year - reg_dob.year - ((_today.month, _today.day) < (reg_dob.month, reg_dob.day))
                        if _age < 18:
                            reg_parent_email = st.text_input(
                                "Parent/Guardian Email",
                                placeholder="parent@example.com",
                                key="reg_parent_email",
                            )
                    reg_submit = st.form_submit_button("Register", use_container_width=True)

                if reg_submit:
                    if user_store is None:
                        st.error("User store module not available.")
                    elif not reg_name.strip() or not reg_email.strip() or not reg_password:
                        st.warning("Name, email, and password are required.")
                    elif reg_password != reg_confirm:
                        st.error("Passwords do not match.")
                    else:
                        _dob_str = reg_dob.isoformat() if reg_dob else ""
                        _role_key = reg_role.lower()
                        _referred_by = st.session_state.get("incoming_ref", "")
                        _ok, _msg = user_store.register_user(
                            email=reg_email.strip(),
                            name=reg_name.strip(),
                            password=reg_password,
                            role=_role_key,
                            dob_str=_dob_str,
                            parent_email=reg_parent_email,
                            referred_by=_referred_by,
                        )
                        if _ok:
                            if _referred_by:
                                st.session_state.pop("incoming_ref", None)
                            # Notify parent if minor
                            if reg_parent_email and email_helper is not None:
                                _sent, _err = email_helper.send_parent_notification(
                                    reg_parent_email,
                                    reg_name.strip(),
                                    reg_email.strip(),
                                )
                                if not _sent:
                                    st.info(f"Account created. Parent notification could not be sent: {_err}")
                            st.success("Registration successful! Please sign in using the Sign In tab.")
                        else:
                            st.error(_msg)

        # ── Tab 2: Google OAuth ───────────────────────────────────────────
        with tab_google:
            try:
                from auth import init_google_auth
                g_auth = init_google_auth()
                if g_auth is None:
                    st.markdown("""
                    <div class="mg-auth-unavailable">
                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none"
                            stroke="currentColor" stroke-width="1.5">
                            <circle cx="12" cy="12" r="10"/>
                            <line x1="12" y1="8" x2="12" y2="12"/>
                            <line x1="12" y1="16" x2="12.01" y2="16"/>
                        </svg>
                        <strong>Google sign-in is not configured</strong>
                        <span>Add your <code>google_credentials.json</code> to the project root,
                        or set <code>GOOGLE_CLIENT_ID</code> and <code>GOOGLE_CLIENT_SECRET</code>
                        in <code>.env</code>, then restart the app.</span>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    g_auth.login()
                    if st.session_state.get("connected"):
                        info = st.session_state.get("user_info", {})
                        _auth_success(
                            email=info.get("email", ""),
                            name=info.get("name", "User"),
                        )
            except ImportError:
                st.markdown(
                    '<div class="mg-auth-unavailable">'
                    "<strong>Google auth package not installed</strong>"
                    "<span>Run: <code>pip install streamlit-google-auth</code></span>"
                    "</div>",
                    unsafe_allow_html=True,
                )
            except Exception as e:
                st.error(f"Google auth error: {e}")

        # ── Tab 3: Local / admin account (streamlit-authenticator) ───────
        with tab_local:
            st.caption("For staff and administrator accounts managed by your institution.")
            try:
                from auth import init_local_auth
                authenticator, _lcfg = init_local_auth()
                result = authenticator.login(location="main")
                _lname, _lstatus, _lusername = result if result else (None, None, None)
                if _lstatus:
                    _lemail = _lcfg["credentials"]["usernames"].get(
                        _lusername, {}
                    ).get("email", _lusername)
                    _auth_success(
                        email=_lemail,
                        name=_lname,
                        role="Admin",
                        role_type="admin",
                    )
                elif _lstatus is False:
                    st.error("Incorrect username or password.")
            except ImportError:
                st.markdown(
                    '<div class="mg-auth-unavailable">'
                    "<strong>Auth package not installed</strong>"
                    "<span>Run: <code>pip install streamlit-authenticator PyYAML</code></span>"
                    "</div>",
                    unsafe_allow_html=True,
                )
            except Exception as e:
                st.warning(f"Local auth unavailable: {e}")


def render_terms_page() -> None:
    """
    Full-page terms screen shown once per server session per user.
    Rendered inline (not as @st.dialog) so st.rerun() fully exits the screen.
    """
    st.markdown("""
    <style>
    .terms-page-wrap {
        max-width: 820px; margin: 2rem auto; background: #ffffff;
        border: 1px solid #d9e3df; border-radius: 12px;
        padding: 2rem 2.4rem 1.6rem; box-shadow: 0 8px 24px rgba(15,23,42,0.07);
    }
    </style>
    <div class="terms-page-wrap">
    <p class="section-label">Required once per session</p>
    <h2>Practitioner Use and Responsibility Agreement</h2>
    <p>This application is a clinical decision-support tool intended for use by trained professionals, including school psychologists, licensed counselors, or designated mental health staff.</p>
    <div class="terms-alert"><strong>Emergency notice:</strong> If someone may be in immediate danger, contact emergency services or a crisis line now. Do not wait for a model result.</div>
    <div class="terms-grid">
        <div class="terms-clause"><strong>Scope of Use</strong><span>You understand that this system identifies potential suicide-related concern in consented data, provides probabilistic signals and summaries, and does not diagnose, predict suicide, or replace clinical judgment. You agree not to use this system as the sole basis for any clinical or disciplinary decision.</span></div>
        <div class="terms-clause"><strong>Human Oversight Required</strong><span>All alerts must be reviewed by a trained human before any action is taken. No automated outreach, escalation, or intervention will occur without professional review. You are responsible for interpreting outputs within proper clinical context.</span></div>
        <div class="terms-clause"><strong>Required Clinical Response</strong><span>You agree to follow an approved response protocol when alerts are generated, such as Brief Suicide Safety Assessment (BSSA), SAFE-T, or an equivalent structured evaluation. You agree not to act on alerts outside established clinical workflows.</span></div>
        <div class="terms-clause"><strong>Non-Punitive Use Policy</strong><span>Data and outputs will not be used for discipline, academic penalties, or behavioural surveillance unrelated to wellbeing. This system is strictly for supportive, health-oriented intervention.</span></div>
        <div class="terms-clause"><strong>Data Responsibility</strong><span>Access only data you are authorised to review. Maintain confidentiality in accordance with institutional policy and applicable law. Avoid downloading or sharing data outside approved systems.</span></div>
        <div class="terms-clause"><strong>Limitations &amp; Risk Awareness</strong><span>The system may produce false positives and false negatives. Absence of an alert does not indicate absence of risk. You retain full responsibility for professional judgment.</span></div>
        <div class="terms-clause"><strong>Accountability</strong><span>All use of this system is logged. Your access and actions may be audited, and misuse may result in loss of access or institutional consequences.</span></div>
        <div class="terms-clause"><strong>Training Requirement</strong><span>You confirm that you are trained in suicide risk assessment and response, understand how to interpret system outputs, and have completed any required onboarding for this tool.</span></div>
        <div class="terms-clause"><strong>Emergency Responsibility</strong><span>This system is not a real-time crisis response service. You remain responsible for appropriate emergency action when imminent risk is identified.</span></div>
        <div class="terms-clause"><strong>Agreement</strong><span>By continuing, you confirm that you are a qualified professional user, will use this system within its intended scope, and accept responsibility for all decisions made using its outputs.</span></div>
    </div>
    </div>
    """, unsafe_allow_html=True)

    accepted = st.checkbox(
        "I confirm that I am a qualified professional user, I agree to this Practitioner "
        "Use and Responsibility Agreement, and I accept responsibility for decisions made "
        "using system outputs.",
        key="terms_consent_checkbox",
    )
    left, _, right = st.columns([1, 2, 1])
    with left:
        if st.button("Sign out", use_container_width=True, key="terms_sign_out"):
            reset_auth_state()
            st.rerun()
    with right:
        if st.button(
            "I consent and continue →",
            use_container_width=True,
            disabled=not accepted,
            key="terms_accept",
            type="primary",
        ):
            _email = st.session_state.get("auth_user", "")
            _terms_consented_emails.add(_email)
            st.session_state.terms_accepted = True
            st.session_state.terms_accepted_at = datetime.datetime.now().isoformat(timespec="seconds")
            st.rerun()

# 4c. Session timeout helper
def check_session_timeout() -> None:
    """Auto-logout after session_timeout_minutes of inactivity. Shows 5-min warning."""
    if not st.session_state.get("authenticated"):
        return
    timeout_mins = st.session_state.get("session_timeout_minutes", 30)
    last = st.session_state.get("last_activity", "")
    if not last:
        st.session_state.last_activity = datetime.datetime.now().isoformat()
        return
    elapsed = (datetime.datetime.now() - datetime.datetime.fromisoformat(last)).total_seconds() / 60
    if elapsed >= timeout_mins:
        reset_auth_state()
        st.warning("You were signed out due to inactivity.")
        st.rerun()
    elif elapsed >= timeout_mins - 5:
        mins_left = int(timeout_mins - elapsed)
        st.warning(f"Your session will expire in ~{mins_left} minute(s) due to inactivity.")


# 5. Auth gate
if not st.session_state["authenticated"]:
    render_sign_in()
    st.stop()

check_session_timeout()

if not st.session_state["terms_accepted"]:
    render_terms_page()
    st.stop()

# 6. Model loading (cached)

@st.cache_resource
def load_model_and_tokenizer():
    """
    Load Mental-RoBERTa in order of availability:
      1. HuggingFace private repo  (HF_REPO_ID + HF_TOKEN  in .env or st.secrets)
      2. Local files               (mindguard_tokenizer/ + mindguard_best_weights.pt)
      3. Base public model         (mental/mental-roberta-base — no fine-tuned weights)
    """
    # Lazy import — avoids Streamlit worker sys.modules conflicts at module load time
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    def _get(key: str, default: str = "") -> str:
        """Read from env var first, fall back to st.secrets."""
        val = os.environ.get(key, "")
        if val:
            return val
        try:
            return st.secrets.get(key, default)
        except Exception:
            return default

    try:
        with open("mindguard_model_config.json") as f:
            config = json.load(f)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        base_model  = config.get("model_name", "mental/mental-roberta-base")
        hf_repo     = _get("HF_REPO_ID")
        hf_token    = _get("HF_TOKEN")
        token_kwargs = {"token": hf_token} if hf_token else {}

        # ── Path 1: HuggingFace repo (weights required; tokenizer optional) ─
        if hf_repo:
            try:
                # Always try weights first — if the repo exists this will work
                weights_path = hf_hub_download(
                    repo_id=hf_repo, filename="mindguard_best_weights.pt", **token_kwargs,
                )
                # Tokenizer: repo subfolder if uploaded, otherwise use base model
                try:
                    tokenizer = AutoTokenizer.from_pretrained(
                        hf_repo, subfolder="mindguard_tokenizer", **token_kwargs,
                    )
                except Exception:
                    tokenizer = AutoTokenizer.from_pretrained(base_model, **token_kwargs)

                # Architecture: local saved model or base model
                local_arch = "mindguard_model_local"
                arch_src   = local_arch if os.path.isdir(local_arch) else base_model
                model = AutoModelForSequenceClassification.from_pretrained(
                    arch_src, num_labels=2, ignore_mismatched_sizes=True,
                )

                # Load fine-tuned weights
                try:
                    state_dict = torch.load(weights_path, map_location=device, weights_only=True)
                except TypeError:
                    # weights_only not supported in older PyTorch builds
                    state_dict = torch.load(weights_path, map_location=device)

                model.load_state_dict(state_dict)
                model = model.to(device)
                model.eval()
                return model, tokenizer, config, device
            except Exception:
                pass  # fall through to local

        # ── Path 2: Local files ────────────────────────────────────────────
        local_tok     = "mindguard_tokenizer"
        local_weights = "mindguard_best_weights.pt"
        if os.path.isdir(local_tok) and os.path.isfile(local_weights):
            tokenizer = AutoTokenizer.from_pretrained(local_tok)
            local_arch = "mindguard_model_local"
            arch_src   = local_arch if os.path.isdir(local_arch) else base_model
            model = AutoModelForSequenceClassification.from_pretrained(
                arch_src, num_labels=2, ignore_mismatched_sizes=True,
            )
            state_dict = torch.load(local_weights, map_location=device, weights_only=True)
            model.load_state_dict(state_dict)
            model = model.to(device)
            model.eval()
            return model, tokenizer, config, device

        # ── Path 3: Base public model (no fine-tuned weights) ─────────────
        tokenizer = AutoTokenizer.from_pretrained(base_model, **token_kwargs)
        model = AutoModelForSequenceClassification.from_pretrained(
            base_model, num_labels=2, ignore_mismatched_sizes=True, **token_kwargs,
        )
        model = model.to(device)
        model.eval()
        st.warning(
            "Running in **base model mode** — fine-tuned weights not found. "
            "Predictions are less accurate. To load the full MindGuard model, "
            "set `HF_REPO_ID` in `.env` **or** run `python save_model_local.py`.",
            icon="⚠️",
        )
        return model, tokenizer, config, device

    except Exception as e:
        st.error(
            f"**Could not load the model.** {e}\n\n"
            "**Setup options:**\n"
            "- Add `HF_REPO_ID=your-hf-username/your-repo` to `.env` (plus `HF_TOKEN`)\n"
            "- Or run `python save_model_local.py` to cache the model locally"
        )
        st.stop()


model, tokenizer, model_config, device = load_model_and_tokenizer()

# 7. Utility functions

def clean_text(text: str) -> str:
    text = str(text).lower()
    text = re.sub(r"http\S+|www\S+", "", text)
    text = re.sub(r"[^a-z\s']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return " ".join(w for w in text.split() if w not in STOPWORDS and len(w) > 2)


def predict_one(text: str):
    enc = tokenizer(
        text, max_length=model_config["max_length"],
        padding="max_length", truncation=True, return_tensors="pt",
    )
    t0 = time.time()
    with torch.no_grad():
        out   = model(input_ids=enc["input_ids"].to(device), attention_mask=enc["attention_mask"].to(device))
        probs = torch.softmax(out.logits, dim=1)
        prob  = probs[0][1].item()
    ms = (time.time() - t0) * 1000
    return prob, ms


def predict_batch(texts: list) -> np.ndarray:
    if not texts:
        return np.array([])
    all_probs = []
    batch_size = 16
    model.eval()
    for i in range(0, len(texts), batch_size):
        batch = texts[i: i + batch_size]
        enc = tokenizer(
            batch, max_length=model_config["max_length"],
            padding="max_length", truncation=True, return_tensors="pt",
        )
        with torch.no_grad():
            out   = model(input_ids=enc["input_ids"].to(device), attention_mask=enc["attention_mask"].to(device))
            probs = torch.softmax(out.logits, dim=1)
            all_probs.extend(probs[:, 1].cpu().numpy())
    return np.array(all_probs)


def risk_label(score: float):
    if score < 0.35:   return "Low Risk",      "#22c55e", "low"
    elif score < 0.55: return "Moderate Risk", "#f59e0b", "medium"
    elif score < 0.75: return "High Risk",     "#f97316", "high"
    else:              return "Critical Risk", "#ef4444", "high"


def update_analytics(prob: float, text: str) -> None:
    a = st.session_state.analytics
    a["total_analyses"] += 1
    cls = "Suicidal" if prob >= 0.5 else "Non-Suicidal"
    if prob >= 0.5:
        a["negative_count"] += 1
    else:
        a["positive_count"] += 1
    a["history"].append({
        "ts": datetime.datetime.now().strftime("%H:%M"),
        "cls": cls,
        "prob": prob,
        "txt": (text[:38] + "...") if len(text) > 38 else text,
    })
    if len(a["history"]) > 10:
        a["history"] = a["history"][-10:]


def run_analysis(text: str):
    prob, ms = predict_one(text)
    update_analytics(prob, text)
    return prob, ms


def build_download_text(text: str, prob: float, ms: float, source: str = "Text") -> str:
    label = "Suicidal / High Risk" if prob >= 0.5 else "Non-Suicidal / Low Risk"
    risk  = "HIGH RISK" if prob >= 0.5 else "LOW RISK"
    conf  = prob if prob >= 0.5 else (1 - prob)
    return (
        f"Source: {source}\nText:\n{text}\n\n"
        f"Prediction: {label}\nRisk: {risk}\nConfidence: {conf:.1%}\n"
        f"Latency: {ms:.1f}ms\nTimestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
    )


def detect_socioeconomic(posts: list) -> dict:
    result = {}
    for cat, kws in SOCIOECONOMIC_KEYWORDS.items():
        found = []
        for kw in kws:
            kw_clean = re.sub(r"[^a-z0-9\s]", " ", kw.lower()).strip()
            if not kw_clean:
                continue
            for post in posts:
                raw = re.sub(r"['\u2019\u2018`]", "", post["text"].lower())
                raw = re.sub(r"[^a-z0-9\s]", " ", raw)
                raw = re.sub(r"\s+", " ", raw)
                if kw_clean in raw:
                    idx = raw.find(kw_clean)
                    start = max(0, idx - 40)
                    end   = min(len(raw), idx + len(kw_clean) + 40)
                    snippet = "..." + raw[start:end].strip() + "..."
                    found.append({"keyword": kw, "snippet": snippet})
                    break
        result[cat] = found
    return result


def clear_text() -> None:
    st.session_state.user_input     = ""
    st.session_state["text_area"]   = ""
    st.session_state.should_analyze = False
    st.session_state.last_result    = None
    st.session_state.download_text  = ""


def extract_text_from_image(image_file) -> str | None:
    try:
        import pytesseract
        img  = Image.open(image_file).convert("RGB")
        text = pytesseract.image_to_string(img, config="--psm 6")
        return text.strip()
    except Exception:
        return None


def gauge(prob: float):
    if prob >= 0.5:
        intensity = (prob - 0.5) * 2; clr = "#dc2626"; lbl = "Suicidal Risk"
    else:
        intensity = (0.5 - prob) * 2; clr = "#0F6E56"; lbl = "Non-Suicidal"
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=intensity * 100,
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": lbl, "font": {"color": "#111827", "size": 11}},
        number={"suffix": "%", "font": {"color": "#111827", "size": 24}},
        gauge={
            "axis": {"range": [None, 100], "tickwidth": 1, "tickcolor": "#6b7280", "tickfont": {"size": 8, "color": "#6b7280"}},
            "bar": {"color": clr},
            "bgcolor": "#ffffff",
            "borderwidth": 1,
            "bordercolor": "#d9e3df",
            "steps": [
                {"range": [0, 33],  "color": "#f8faf9"},
                {"range": [33, 66], "color": "#eef4f1"},
                {"range": [66, 100],"color": "#e5ede9"},
            ],
            "threshold": {"line": {"color": "#111827", "width": 2}, "thickness": 0.65, "value": 80},
        },
    ))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font={"color": "#111827"}, height=165, margin=dict(l=6, r=6, t=28, b=2))
    return fig


def timeline_chart(df, date_col: str = "date", score_col: str = "risk_score"):
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], utc=True, errors="coerce")
    df = df.dropna(subset=[date_col])
    df["week"] = df[date_col].dt.to_period("W").dt.start_time
    weekly = (
        df.groupby("week")[score_col]
        .agg(["mean", "max", "count"])
        .reset_index()
        .rename(columns={"mean": "avg", "max": "peak", "count": "posts"})
    )
    fig = go.Figure()
    for y0, y1, col, lbl in [
        (0.00, 0.35, "rgba(34,197,94,0.07)",  "Low"),
        (0.35, 0.55, "rgba(245,158,11,0.07)", "Moderate"),
        (0.55, 0.75, "rgba(249,115,22,0.07)", "High"),
        (0.75, 1.00, "rgba(239,68,68,0.09)",  "Critical"),
    ]:
        fig.add_hrect(y0=y0, y1=y1, fillcolor=col, line_width=0, annotation_text=lbl, annotation_position="right", annotation=dict(font_color="#6b7280", font_size=9))
    fig.add_bar(x=weekly["week"], y=weekly["posts"], name="Posts/week", marker_color="rgba(13,148,136,0.2)", yaxis="y2", hovertemplate="Week %{x}<br>Posts: %{y}<extra></extra>")
    fig.add_scatter(x=weekly["week"], y=weekly["avg"],  mode="lines+markers", name="Avg risk",  line=dict(color="#0F6E56", width=2),   marker=dict(size=5, color="#0F6E56"), hovertemplate="%{x}<br>Avg: %{y:.1%}<extra></extra>")
    fig.add_scatter(x=weekly["week"], y=weekly["peak"], mode="lines",         name="Peak risk", line=dict(color="#dc2626", width=1.5, dash="dot"), hovertemplate="%{x}<br>Peak: %{y:.1%}<extra></extra>")
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#ffffff", font_color="#4b5563",
        yaxis=dict(title="Risk", tickformat=".0%", range=[0, 1], gridcolor="#e5e7eb", color="#4b5563"),
        yaxis2=dict(overlaying="y", side="right", showgrid=False, color="#6b7280"),
        xaxis=dict(gridcolor="#e5e7eb", color="#4b5563"),
        legend=dict(orientation="h", y=-0.22, font_color="#4b5563", font_size=10),
        margin=dict(l=40, r=50, t=10, b=40), height=270,
    )
    return fig


def render_post_cards(df, score_col="risk_score", text_col="text", date_col="date", sub_col=None, url_col=None, type_col=None, n=20) -> None:
    for _, row in df.sort_values(score_col, ascending=False).head(n).iterrows():
        score = row[score_col]
        lbl, col, cls = risk_label(score)
        preview = str(row[text_col])[:250] + ("..." if len(str(row[text_col])) > 250 else "")
        try:
            date_s = pd.to_datetime(row[date_col]).strftime("%d %b %Y")
        except Exception:
            date_s = str(row.get(date_col, ""))
        meta = ""
        if sub_col and sub_col in row:  meta += f"r/{row[sub_col]}  "
        if type_col and type_col in row: meta += f"{row[type_col]}  "
        meta += date_s
        link = ""
        if url_col and url_col in row and row[url_col]:
            link = f'<a href="{row[url_col]}" target="_blank" style="color:#0F6E56;font-size:0.68rem;text-decoration:none">View source</a>'
        st.markdown(
            f'<div class="post-card {cls}">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">'
            f'<span style="color:#6b7280;font-size:0.68rem">{meta}</span>'
            f'<span style="color:{col};font-weight:700;font-size:0.76rem">{score:.1%} — {lbl}</span>'
            f'</div><p style="color:#4b5563;margin:0;font-size:0.74rem;line-height:1.5">{preview}</p>{link}</div>',
            unsafe_allow_html=True,
        )


def render_socio(signals: dict) -> None:
    any_found = any(len(v) > 0 for v in signals.values())
    if not any_found:
        st.info("No socio-economic distress keywords detected in this content.")
        return
    total = sum(len(v) for v in signals.values())
    st.markdown(
        f'<p style="font-size:0.78rem;color:#4b5563;margin-bottom:0.5rem">'
        f'<strong style="color:#0F6E56">{total}</strong> socio-economic distress signal(s) detected across '
        f'<strong style="color:#0F6E56">{sum(1 for v in signals.values() if v)}</strong> categories.</p>',
        unsafe_allow_html=True,
    )
    for cat, items in signals.items():
        if not items:
            continue
        st.markdown(
            f'<p style="font-size:0.78rem;font-weight:700;margin:0.6rem 0 0.15rem;color:#111827">'
            f'{cat} <span style="color:#0F6E56;font-weight:400;font-size:0.72rem">({len(items)} signal(s))</span></p>',
            unsafe_allow_html=True,
        )
        for item in items:
            kw      = item["keyword"] if isinstance(item, dict) else item
            snippet = item.get("snippet", "") if isinstance(item, dict) else ""
            st.markdown(
                f'<div style="background:#eaf7f2;border-radius:8px;padding:0.4rem 0.65rem;margin:0.18rem 0;border-left:3px solid #0F6E56;">'
                f'<span style="color:#0F6E56;font-weight:700;font-size:0.76rem">{kw}</span>'
                + (f'<br><span style="color:#6b7280;font-size:0.7rem;font-style:italic">{snippet}</span>' if snippet else "")
                + "</div>",
                unsafe_allow_html=True,
            )
    found_cats = {c: len(v) for c, v in signals.items() if v}
    if len(found_cats) > 1:
        fig = px.pie(
            names=list(found_cats.keys()), values=list(found_cats.values()),
            hole=0.45, color_discrete_sequence=["#0d9488","#7c3aed","#f97316","#f59e0b","#ef4444","#22c55e"],
        )
        fig.update_traces(textposition="outside", textinfo="label+percent")
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#4b5563", margin=dict(t=10, b=10, l=10, r=10), height=260, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)


def format_contact(contact: str) -> str:
    if contact.startswith("http://") or contact.startswith("https://"):
        return f'<a href="{contact}" target="_blank">{contact}</a>'
    if contact.endswith((".com", ".org", ".info", ".net")):
        return f'<a href="https://{contact}" target="_blank">{contact}</a>'
    return f"<span>{contact}</span>"


def render_resource_card(r: dict, border_color: str = "#7c3aed") -> None:
    st.markdown(
        f'<div class="resource-card" style="border-left-color:{border_color}">'
        f'<div class="resource-name">{r["name"]}</div>'
        f'<div class="resource-type">{r["type"]}</div>'
        f'<div class="resource-contact">{format_contact(r["contact"])}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_resources(region: str) -> None:
    for r in RESOURCES[region]:
        render_resource_card(r)


def overall_banner(score: float, n_posts: int, n_high: int, period: str) -> None:
    lbl, col, _ = risk_label(score)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Overall Risk", f"{score:.1%}")
    m2.metric("Posts Analysed", str(n_posts))
    m3.metric("High-Risk Posts", str(n_high))
    m4.metric("Period", period)
    st.markdown(
        f'<div style="display:inline-block;padding:5px 16px;border-radius:8px;background:{col}22;'
        f'color:{col};border:1.5px solid {col};font-weight:700;font-size:0.88rem;margin:4px 0">{lbl}</div>',
        unsafe_allow_html=True,
    )
    if score >= 0.55:
        st.error("CRISIS ALERT — High-risk content detected. Please direct to crisis resources.")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_reddit(username: str, client_id: str, client_secret: str) -> list:
    import praw
    reddit = praw.Reddit(client_id=client_id, client_secret=client_secret, user_agent="MindGuard:v3.0 (mental health research)")
    posts = []
    try:
        redditor = reddit.redditor(username)
        for sub in redditor.submissions.new(limit=200):
            dt = datetime.datetime.fromtimestamp(sub.created_utc, tz=datetime.timezone.utc)
            if dt < SIX_MONTHS_AGO: break
            text = f"{sub.title} {sub.selftext}".strip()
            if len(text) > 10:
                posts.append({"text": text, "date": dt, "subreddit": str(sub.subreddit), "type": "post", "url": f"https://reddit.com{sub.permalink}"})
        for c in redditor.comments.new(limit=500):
            dt = datetime.datetime.fromtimestamp(c.created_utc, tz=datetime.timezone.utc)
            if dt < SIX_MONTHS_AGO: break
            text = c.body.strip()
            if len(text) > 10 and text not in ("[deleted]", "[removed]"):
                posts.append({"text": text, "date": dt, "subreddit": str(c.subreddit), "type": "comment", "url": f"https://reddit.com{c.permalink}"})
    except Exception as e:
        raise RuntimeError(str(e))
    posts.sort(key=lambda x: x["date"])
    return posts


def download_audio(url: str, out_dir: str) -> str:
    """Download audio and trim to first 5 minutes."""
    out_template = os.path.join(out_dir, "audio.%(ext)s")
    cmd = ["yt-dlp","--extract-audio","--audio-format","mp3","--audio-quality","5","--no-playlist","--quiet","-o", out_template, url]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    if result.returncode != 0:
        raise RuntimeError(f"Download failed: {result.stderr.strip()}")
    mp3 = os.path.join(out_dir, "audio.mp3")
    if not os.path.exists(mp3):
        files = list(Path(out_dir).glob("audio.*"))
        if not files:
            raise RuntimeError("Audio file not found after download.")
        mp3 = str(files[0])
    trimmed = os.path.join(out_dir, "audio_trimmed.mp3")
    trim_cmd = ["ffmpeg","-i", mp3,"-t","300","-acodec","libmp3lame","-q:a","5","-y", trimmed,"-loglevel","error"]
    try:
        trim_result = subprocess.run(trim_cmd, capture_output=True, timeout=60)
        if trim_result.returncode == 0 and os.path.exists(trimmed) and os.path.getsize(trimmed) > 1000:
            return trimmed
    except Exception as _e:
        st.warning(f"Audio trim failed: {_e}")
    return mp3


def transcribe_audio(audio_path: str) -> str:
    from faster_whisper import WhisperModel
    wm = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, _ = wm.transcribe(audio_path, beam_size=3)
    return " ".join(seg.text.strip() for seg in segments).strip()


def bluesky_login(identifier: str, password: str) -> str:
    import urllib.request
    url     = "https://bsky.social/xrpc/com.atproto.server.createSession"
    payload = json.dumps({"identifier": identifier, "password": password}).encode()
    req     = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "MindGuard/3.0"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
            return data["accessJwt"]
    except Exception as e:
        raise RuntimeError(f"Bluesky login failed: {e}")


def fetch_bluesky(handle: str, access_token: str = None) -> list:
    import urllib.request
    import urllib.error
    handle = handle.strip().lstrip("@")
    if "." not in handle:
        handle = f"{handle}.bsky.social"
    cutoff  = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)
    headers = {"User-Agent": "MindGuard/3.0"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    resolve_url = f"https://bsky.social/xrpc/com.atproto.identity.resolveHandle?handle={handle}"
    try:
        req = urllib.request.Request(resolve_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            did = json.loads(r.read().decode())["did"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Handle not found: {handle} (HTTP {e.code}).")
    except Exception as e:
        raise RuntimeError(f"Could not reach Bluesky API: {e}")
    posts = []; cursor = None
    for _ in range(10):
        params   = f"actor={did}&limit=100"
        if cursor: params += f"&cursor={cursor}"
        feed_url = f"https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed?{params}"
        try:
            req = urllib.request.Request(feed_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Could not fetch posts (HTTP {e.code}). Provide Bluesky credentials.")
        except Exception as e:
            raise RuntimeError(f"Could not fetch posts: {e}")
        feed = data.get("feed", [])
        if not feed: break
        oldest_in_page = None
        for item in feed:
            post    = item.get("post", {})
            record  = post.get("record", {})
            created = record.get("createdAt", "")
            try:
                dt = datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))
            except Exception:
                continue
            oldest_in_page = dt
            if dt < cutoff: continue
            text = record.get("text", "").strip()
            if len(text) > 5:
                uri  = post.get("uri", "")
                rkey = uri.split("/")[-1] if uri else ""
                posts.append({"text": text, "date": dt, "url": f"https://bsky.app/profile/{handle}/post/{rkey}"})
        cursor = data.get("cursor")
        if not cursor: break
        if oldest_in_page and oldest_in_page < cutoff: break
    posts.sort(key=lambda x: x["date"])
    return posts


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_mastodon(handle: str) -> list:
    import urllib.request
    if "@" not in handle:
        raise RuntimeError("Mastodon handle must be in format: username@instance.social")
    parts = handle.lstrip("@").split("@")
    if len(parts) != 2:
        raise RuntimeError("Mastodon handle must be in format: username@instance.social")
    username, instance = parts
    search_url = f"https://{instance}/api/v1/accounts/lookup?acct={username}"
    try:
        with urllib.request.urlopen(search_url, timeout=10) as r:
            account    = json.loads(r.read())
            account_id = account["id"]
    except Exception as e:
        raise RuntimeError(f"Could not find Mastodon account: {e}")
    posts = []; max_id = None
    for _ in range(10):
        params     = "limit=40&exclude_replies=false"
        if max_id: params += f"&max_id={max_id}"
        status_url = f"https://{instance}/api/v1/accounts/{account_id}/statuses?{params}"
        try:
            with urllib.request.urlopen(status_url, timeout=10) as r:
                statuses = json.loads(r.read())
        except Exception:
            break
        if not statuses: break
        for s in statuses:
            created = s.get("created_at", "")
            try:
                dt = datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))
            except Exception:
                continue
            if dt < THREE_MONTHS_AGO: break
            content = re.sub(r"<[^>]+>", "", s.get("content", "")).strip()
            if len(content) > 5:
                posts.append({"text": content, "date": dt, "url": s.get("url", "")})
        max_id = statuses[-1]["id"]
        if posts and posts[-1]["date"] < THREE_MONTHS_AGO: break
    posts = [p for p in posts if p["date"] >= THREE_MONTHS_AGO]
    posts.sort(key=lambda x: x["date"])
    return posts


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_youtube(channel_input: str, api_key: str) -> list:
    import urllib.request
    import urllib.parse
    BASE = "https://www.googleapis.com/youtube/v3"

    def yt_get(endpoint, params):
        params["key"] = api_key
        url = f"{BASE}/{endpoint}?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read())

    channel_id = None
    if "youtube.com/channel/" in channel_input:
        channel_id = channel_input.split("youtube.com/channel/")[-1].split("/")[0].split("?")[0]
    elif "youtube.com/@" in channel_input:
        handle = channel_input.split("youtube.com/@")[-1].split("/")[0].split("?")[0]
        data   = yt_get("channels", {"part": "id", "forHandle": handle})
        items  = data.get("items", [])
        if items: channel_id = items[0]["id"]
    else:
        data  = yt_get("channels", {"part": "id", "forHandle": channel_input.lstrip("@")})
        items = data.get("items", [])
        if items: channel_id = items[0]["id"]
    if not channel_id:
        raise RuntimeError("Could not resolve YouTube channel. Use a channel URL or @handle.")
    cutoff      = THREE_MONTHS_AGO.strftime("%Y-%m-%dT%H:%M:%SZ")
    search_data = yt_get("search", {"part": "id,snippet", "channelId": channel_id, "type": "video", "order": "date", "maxResults": 50, "publishedAfter": cutoff})
    posts = []
    for item in search_data.get("items", []):
        video_id  = item["id"].get("videoId", "")
        snippet   = item.get("snippet", {})
        title     = snippet.get("title", "")
        desc      = snippet.get("description", "")
        published = snippet.get("publishedAt", "")
        try:
            dt = datetime.datetime.fromisoformat(published.replace("Z", "+00:00"))
        except Exception:
            continue
        text = f"{title} {desc}".strip()
        if len(text) > 5:
            posts.append({"text": text, "date": dt, "url": f"https://youtube.com/watch?v={video_id}", "video_id": video_id})
        try:
            comments_data = yt_get("commentThreads", {"part": "snippet", "videoId": video_id, "maxResults": 20, "order": "relevance"})
            for c in comments_data.get("items", []):
                comment_text = c["snippet"]["topLevelComment"]["snippet"].get("textDisplay", "")
                comment_text = re.sub(r"<[^>]+>", "", comment_text).strip()
                if len(comment_text) > 5:
                    posts.append({"text": comment_text, "date": dt, "url": f"https://youtube.com/watch?v={video_id}", "video_id": video_id})
        except Exception:
            pass  # comment fetch is best-effort, video still analyzed
    posts.sort(key=lambda x: x["date"])
    return posts


def parse_whatsapp_line(line: str):
    m = re.match(r"\[(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4}),\s*(\d{1,2}):(\d{2})(?::\d{2})?\]\s*([^:]+):\s*(.+)", line)
    if m:
        day, month, year, hour, minute, sender, msg = m.groups()
        year = int(year); year = year + 2000 if year < 100 else year
        try:
            dt = datetime.datetime(year, int(month), int(day), int(hour), int(minute), tzinfo=datetime.timezone.utc)
            return dt, sender.strip(), msg.strip()
        except Exception:
            pass
    m = re.match(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4}),\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*-\s*([^:]+):\s*(.+)", line)
    if m:
        day, month, year, hour, minute, sender, msg = m.groups()
        year = int(year); year = year + 2000 if year < 100 else year
        try:
            dt = datetime.datetime(year, int(month), int(day), int(hour), int(minute), tzinfo=datetime.timezone.utc)
            return dt, sender.strip(), msg.strip()
        except Exception:
            pass
    return None


def parse_uploaded_file(uploaded_file) -> list:
    posts = []; name = uploaded_file.name.lower(); content = uploaded_file.read()
    if name.endswith(".txt"):
        text = content.decode("utf-8", errors="ignore"); lines = text.split("\n")
        whatsapp_hits = sum(1 for l in lines[:20] if re.search(r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}.*\d{1,2}:\d{2}", l))
        is_whatsapp   = whatsapp_hits >= 2
        if is_whatsapp:
            skip_phrases = ["messages and calls are end-to-end encrypted","message was deleted","you deleted this message","missed voice call","missed video call","image omitted","video omitted","audio omitted","document omitted","sticker omitted","gif omitted","contact card omitted","location omitted","this message was deleted","changed the subject","changed this group","added you","left","joined using this group"]
            for line in lines:
                line = line.strip()
                if not line: continue
                parsed = parse_whatsapp_line(line)
                if parsed:
                    dt, sender, msg = parsed
                    if any(skip in msg.lower() for skip in skip_phrases): continue
                    if len(msg) < 3: continue
                    posts.append({"text": msg, "date": dt, "url": "", "sender": sender})
                elif posts and len(line) > 3:
                    posts[-1]["text"] += " " + line
        else:
            valid_lines = [l.strip() for l in lines if len(l.strip()) > 10]
            for i, line in enumerate(valid_lines):
                dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=i)
                posts.append({"text": line, "date": dt, "url": ""})
    elif name.endswith(".csv"):
        import io
        df       = pd.read_csv(io.BytesIO(content))
        text_col = next((c for c in df.columns if any(k in c.lower() for k in ["text","content","message","post","body","tweet","comment"])), None)
        if text_col is None and len(df.columns) > 0: text_col = df.columns[0]
        date_col = next((c for c in df.columns if any(k in c.lower() for k in ["date","time","created","timestamp"])), None)
        for i, row in df.iterrows():
            text = str(row[text_col]).strip() if text_col else ""
            if len(text) < 5: continue
            dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=i)
            if date_col:
                try: dt = pd.to_datetime(row[date_col], utc=True)
                except Exception: pass  # date column inference is best-effort
            posts.append({"text": text, "date": dt, "url": ""})
    elif name.endswith(".json"):
        try:
            data = json.loads(content.decode("utf-8", errors="ignore"))
        except Exception:
            return posts
        if isinstance(data, list):
            for item in data:
                if "timestamp" in item and "data" in item:
                    ts   = item.get("timestamp", 0)
                    dt   = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
                    text = ""
                    for d in item.get("data", []):
                        if isinstance(d, dict):
                            text += d.get("post", {}).get("message", "") if isinstance(d.get("post"), dict) else str(d.get("post", ""))
                    if not text: text = item.get("title", "")
                    if len(text.strip()) > 5: posts.append({"text": text.strip(), "date": dt, "url": ""})
                elif "tweet" in item:
                    tweet   = item["tweet"]
                    text    = tweet.get("full_text", tweet.get("text", "")).strip()
                    created = tweet.get("created_at", "")
                    dt      = datetime.datetime.now(datetime.timezone.utc)
                    try: dt = datetime.datetime.strptime(created, "%a %b %d %H:%M:%S +0000 %Y").replace(tzinfo=datetime.timezone.utc)
                    except Exception: pass
                    if len(text) > 5 and not text.startswith("RT @"):
                        posts.append({"text": text, "date": dt, "url": f"https://twitter.com/i/web/status/{tweet.get('id_str','')}"})
        elif isinstance(data, dict):
            tweets = data.get("tweets", data.get("data", []))
            if isinstance(tweets, list):
                for item in tweets:
                    tweet   = item.get("tweet", item)
                    text    = tweet.get("full_text", tweet.get("text", "")).strip()
                    created = tweet.get("created_at", "")
                    dt      = datetime.datetime.now(datetime.timezone.utc)
                    try: dt = datetime.datetime.strptime(created, "%a %b %d %H:%M:%S +0000 %Y").replace(tzinfo=datetime.timezone.utc)
                    except Exception: pass
                    if len(text) > 5 and not text.startswith("RT @"):
                        posts.append({"text": text, "date": dt, "url": ""})
    return posts


def _run_scraper_worker(platform: str, url: str, months: int) -> list:
    import sys as _sys
    worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scraper_worker.py")
    result = subprocess.run([_sys.executable, worker, platform, url, str(months)], capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        err = result.stderr.strip().split("\n")[-1] if result.stderr else "Unknown error"
        raise RuntimeError(err)
    try:
        data = json.loads(result.stdout.strip())
    except Exception:
        raise RuntimeError(f"Could not parse scraper output: {result.stdout[:300]}")
    if not data.get("ok"):
        raise RuntimeError(data.get("error", "Scraper failed"))
    posts = []
    for p in data.get("posts", []):
        try:
            dt = datetime.datetime.fromisoformat(p["date"]).replace(tzinfo=datetime.timezone.utc)
        except Exception:
            dt = datetime.datetime.now(datetime.timezone.utc)
        posts.append({"text": p["text"], "date": dt, "url": p["url"]})
    return posts


def scrape_facebook_public(profile_url: str, months: int = 3) -> list:
    return _run_scraper_worker("facebook", profile_url, months)


def scrape_twitter_public(profile_url: str, months: int = 3) -> list:
    return _run_scraper_worker("twitter", profile_url, months)


# 8. main_app()

def main_app() -> None:
    # Inject the MindGuard UI overhaul CSS + Tabler icons CDN here so that
    # pre-auth screens (sign-in, terms) keep their original light styling.
    st.markdown(MG_UI_CSS, unsafe_allow_html=True)

    # Update last activity for session timeout tracking
    st.session_state.last_activity = datetime.datetime.now().isoformat()

    # Load referral code from user store if not already set
    if not st.session_state.get("referral_code") and user_store is not None:
        _u = user_store.get_user(st.session_state.auth_user)
        if _u:
            st.session_state.referral_code = _u.get("referral_code", "")

    # Load unread notifications
    _unread_list = []
    if notifications_store is not None:
        _unread_list = notifications_store.get_unread_for_user(st.session_state.auth_user)
    st.session_state.notifications_unread = len(_unread_list)
    _unread_count = st.session_state.notifications_unread

    # Identity bits
    _name = st.session_state.get("auth_name") or st.session_state.get("auth_user", "User")
    _email = st.session_state.get("auth_user", "")
    _role_type = st.session_state.get("auth_role_type", "counselor")
    _initials = "".join(p[0].upper() for p in _name.split()[:2]) if _name else "MG"

    # ── SIDEBAR (dark, primary navigation) ────────────────────────────
    with st.sidebar:
        # Brand
        st.markdown(
            '<div class="mg-sb-brand">'
            '<div class="mg-sb-logo">MG</div>'
            '<div class="mg-sb-name">MindGuard</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        # Role section label
        st.markdown(
            f'<div class="mg-sb-section">{_role_type.capitalize()}</div>',
            unsafe_allow_html=True,
        )

        _pages = [
            ("dashboard",   "ti-brain",          "Dashboard"),
            ("reddit",      "ti-brand-reddit",   "Reddit"),
            ("video",       "ti-video",          "Video"),
            ("bluesky",     "ti-butterfly",      "Bluesky"),
            ("mastodon",    "ti-cloud",          "Mastodon"),
            ("youtube",     "ti-brand-youtube",  "YouTube"),
            ("file",        "ti-folder-open",    "File Upload"),
            ("facebook",    "ti-brand-facebook", "Facebook"),
            ("twitter",     "ti-brand-x",        "Twitter / X"),
            ("unified",     "ti-share",          "Multi-Platform"),
            ("resources",   "ti-ambulance",      "Crisis Resources"),
            ("team",        "ti-users",          "Team"),
        ]
        _current = st.session_state.get("mg_page", "dashboard")
        for _page_key, _icon, _label in _pages:
            if _page_key == _current:
                st.markdown(
                    f'<div class="mg-sb-active">'
                    f'<i class="ti {_icon}"></i> {_label}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                if st.button(_label, key=f"nav_{_page_key}", use_container_width=True):
                    st.session_state.mg_page = _page_key
                    st.rerun()

        # Footer — user identity
        st.markdown(
            f'<div class="mg-sb-footer">'
            f'<div class="mg-sb-avatar">{_initials}</div>'
            f'<div style="flex:1;min-width:0">'
            f'<div class="mg-sb-uname">{_name}</div>'
            f'<div class="mg-sb-uemail">{_email}</div>'
            f'</div>'
            f'<div class="mg-sb-pill">{_role_type.capitalize()}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── TOPBAR ────────────────────────────────────────────────────────
    _page_titles = {
        "dashboard": "Text / Image Analysis",
        "reddit":    "Reddit Analysis",
        "video":     "Video Analysis",
        "bluesky":   "Bluesky Analysis",
        "mastodon":  "Mastodon Analysis",
        "youtube":   "YouTube Analysis",
        "file":      "File Upload Analysis",
        "facebook":  "Facebook Analysis",
        "twitter":   "Twitter / X Analysis",
        "unified":   "Multi-Platform Profile",
        "resources": "Crisis Resources",
        "team":      "Team",
    }
    _page_title = _page_titles.get(_current, "MindGuard")
    _bell_dot = '<div class="mg-bell-dot"></div>' if _unread_count > 0 else ""
    st.markdown(
        f'<div class="mg-topbar">'
        f'<div class="mg-topbar-title">{_page_title}</div>'
        f'<div class="mg-topbar-right">'
        f'<div class="mg-topbar-bell"><i class="ti ti-bell"></i>{_bell_dot}</div>'
        f'<div class="mg-topbar-av">{_initials}</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Sign-out (small, top-right)
    _tb_l, _tb_r = st.columns([10, 1])
    with _tb_r:
        if st.button("Sign out", key="topbar_signout", help="Sign out"):
            reset_auth_state()
            st.rerun()

    # Notifications inbox (when there are unread)
    if _unread_list:
        with st.expander(f"🔔 {_unread_count} unread notification(s)", expanded=False):
            if st.button("Mark all as read", key="notif_mark_all_read"):
                for _n in _unread_list:
                    notifications_store.mark_read(_n["id"], st.session_state.auth_user)
                st.rerun()
            for _notif in _unread_list:
                _subj = _notif.get("subject", "(no subject)")
                _date = _notif.get("timestamp", "")[:10]
                col_txt, col_btn = st.columns([5, 1])
                with col_txt:
                    st.markdown(f"**{_subj}** · {_date}")
                    st.caption(f"From: {_notif.get('sender','')}")
                    st.markdown(_notif.get("body", ""))
                with col_btn:
                    if st.button("✓", key=f"notif_read_{_notif['id']}", help="Mark as read"):
                        notifications_store.mark_read(_notif["id"], st.session_state.auth_user)
                        st.rerun()

    # Admin: send notification
    if _role_type == "admin" and notifications_store is not None:
        with st.expander("📢 Send notification", expanded=False):
            _notif_subject    = st.text_input("Subject", key="admin_notif_subject")
            _notif_body       = st.text_area("Message", key="admin_notif_body", height=90)
            _notif_target_opt = st.selectbox("To", ["All users", "Specific email"], key="admin_notif_target_opt")
            _notif_target     = "all"
            if _notif_target_opt == "Specific email":
                _notif_target = st.text_input("Recipient email", key="admin_notif_target_email")
            if st.button("Send", key="admin_notif_send"):
                if _notif_subject and _notif_body:
                    notifications_store.create_notification(
                        sender_email=st.session_state.auth_user,
                        target=_notif_target if _notif_target else "all",
                        subject=_notif_subject,
                        body=_notif_body,
                    )
                    st.success("Notification sent.")
                else:
                    st.warning("Subject and message are required.")

    # Referral link
    _ref = st.session_state.get("referral_code", "")
    if _ref:
        with st.expander("🔗 Share referral link", expanded=False):
            _base_url = os.environ.get("APP_BASE_URL", "http://localhost:8501")
            st.caption("Share this link to invite others:")
            st.code(f"{_base_url}?ref={_ref}", language=None)

    # Reusable: render a single team card
    def render_team_card(member: dict) -> None:
        st.markdown(f"""
        <div class="team-card">
            <img src="{member["image"]}" alt="{member["name"]}">
            <div class="team-card-body">
                <div class="team-name">{member["name"]}</div>
                <div class="team-role">{member["role"]}</div>
                <div class="team-bio">{member["bio"]}</div>
                <a class="team-link" href="{member["linkedin"]}" target="_blank">LinkedIn profile</a>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ── PAGE ROUTING ──────────────────────────────────────────────────
    # Dashboard: 3-column Input | Prediction | Analytics
    if _current == "dashboard":
        col_input, col_pred, col_analytics = st.columns([1, 1.2, 1])

        # ── Input panel ────────────────────────────────────────────────
        with col_input:
            st.markdown(
                '<div class="mg-panel"><div class="mg-panel-title">'
                '<i class="ti ti-pencil"></i> Input</div>',
                unsafe_allow_html=True,
            )
            m1, m2 = st.columns(2)
            with m1:
                if st.button("Type Text", use_container_width=True, key="mode_text_btn"):
                    st.session_state.input_mode = "text"; st.rerun()
            with m2:
                if st.button("Upload Image", use_container_width=True, key="mode_image_btn"):
                    st.session_state.input_mode = "image"; st.rerun()

            if st.session_state.input_mode == "text":
                with st.expander("Try a sample", expanded=False):
                    for label, tweet in SAMPLE_TWEETS.items():
                        if st.button(label, key=f"sample_{label}", use_container_width=True):
                            st.session_state.user_input = tweet
                            st.session_state["text_area"] = tweet
                            st.session_state.should_analyze = True
                            st.rerun()
                user_input = st.text_area(
                    "Enter text to analyse:",
                    height=108,
                    placeholder="Type or paste text here...",
                    value=st.session_state.user_input,
                    key="text_area",
                )
                st.session_state.user_input = user_input
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("Analyse", use_container_width=True, key="analyse_btn"):
                        if user_input.strip():
                            st.session_state.should_analyze = True
                        else:
                            st.warning("Enter some text first.")
                with b2:
                    if st.button("Clear", use_container_width=True, key="clear_btn"):
                        clear_text(); st.rerun()
            else:
                uploaded_img = st.file_uploader(
                    "Upload an image",
                    type=["png", "jpg", "jpeg", "webp"],
                    key="img_upload",
                )
                if uploaded_img:
                    img_text = extract_text_from_image(uploaded_img)
                    if img_text:
                        st.session_state.user_input = img_text
                        st.session_state.should_analyze = True
                        st.success(f"Extracted {len(img_text)} characters from image.")
                    else:
                        st.error("Could not extract text. Ensure the image contains readable text and pytesseract is installed.")
            # Run inference once per click
            if st.session_state.should_analyze and st.session_state.user_input.strip():
                prob, ms = run_analysis(st.session_state.user_input)
                st.session_state.last_result   = {"prob": prob, "ms": ms, "text": st.session_state.user_input}
                st.session_state.download_text = build_download_text(st.session_state.user_input, prob, ms)
                st.session_state.should_analyze = False
            st.markdown('</div>', unsafe_allow_html=True)

        # ── Prediction panel ───────────────────────────────────────────
        with col_pred:
            st.markdown(
                '<div class="mg-panel"><div class="mg-panel-title">'
                '<i class="ti ti-chart-donut"></i> Prediction</div>',
                unsafe_allow_html=True,
            )
            res = st.session_state.last_result
            if res is None:
                st.markdown(
                    '<div style="text-align:center;padding:2.4rem 1rem;color:#9ca3af;font-size:0.78rem">'
                    'Enter text and click Analyse.</div>',
                    unsafe_allow_html=True,
                )
            else:
                prob = res["prob"]; ms = res["ms"]
                _lbl, _color, _cls = risk_label(prob)
                conf = prob if prob >= 0.5 else (1 - prob)
                st.plotly_chart(gauge(prob), use_container_width=True, config={"displayModeBar": False})
                st.markdown(f"""
<div class="mg-risk-row">
  <div class="mg-risk-stat"><div class="mg-risk-val" style="color:{_color}">{prob:.0%}</div><div class="mg-risk-lbl">Risk Score</div></div>
  <div class="mg-risk-stat"><div class="mg-risk-val" style="color:{_color}">{conf:.0%}</div><div class="mg-risk-lbl">Confidence</div></div>
  <div class="mg-risk-stat"><div class="mg-risk-val">{ms:.0f}ms</div><div class="mg-risk-lbl">Latency</div></div>
</div>
""", unsafe_allow_html=True)
                if prob >= 0.5:
                    st.markdown(
                        '<div class="mg-alert-box"><i class="ti ti-alert-triangle"></i> '
                        'Crisis alert — high-risk language detected</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        '<div class="mg-safe-box"><i class="ti ti-circle-check"></i> '
                        'No high-risk signals detected</div>',
                        unsafe_allow_html=True,
                    )
                if st.session_state.download_text:
                    st.download_button(
                        "Download report",
                        st.session_state.download_text,
                        file_name="mindguard_report.txt",
                        use_container_width=True,
                    )
            st.markdown('</div>', unsafe_allow_html=True)

        # ── Session analytics panel ───────────────────────────────────
        with col_analytics:
            st.markdown(
                '<div class="mg-panel"><div class="mg-panel-title">'
                '<i class="ti ti-chart-bar"></i> Session Analytics</div>',
                unsafe_allow_html=True,
            )
            a = st.session_state.analytics
            total = a["total_analyses"]
            if total == 0:
                st.markdown(
                    '<div style="text-align:center;padding:1.6rem 1rem;color:#9ca3af;font-size:0.78rem">'
                    'No analyses yet.</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(f"""
<div class="mg-stat-row">
  <div class="mg-stat-card"><div class="mg-stat-num">{total}</div><div class="mg-stat-lbl">Analysed</div></div>
  <div class="mg-stat-card"><div class="mg-stat-num" style="color:#dc2626">{a['negative_count']}</div><div class="mg-stat-lbl">At-Risk</div></div>
  <div class="mg-stat-card"><div class="mg-stat-num" style="color:#10b981">{a['positive_count']}</div><div class="mg-stat-lbl">Safe</div></div>
</div>
""", unsafe_allow_html=True)
                st.markdown(
                    '<div style="font-size:0.6rem;font-weight:700;color:#0F766E;text-transform:uppercase;'
                    'letter-spacing:0.1em;margin-bottom:6px;padding-bottom:6px;'
                    'border-bottom:0.5px solid #f1f5f9">Recent history</div>',
                    unsafe_allow_html=True,
                )
                for entry in reversed(a.get("history", [])[-5:]):
                    _cls_label = entry.get("cls", "Unknown")
                    _cls_class = "risk" if _cls_label == "Suicidal" else "safe"
                    _txt = entry.get("txt", "")
                    _ts = entry.get("ts", "")
                    st.markdown(
                        f'<div class="mg-history-row">'
                        f'<span class="mg-h-cls {_cls_class}">{_cls_label}</span>'
                        f'<span class="mg-h-ts">{_ts}</span>'
                        f'<span class="mg-h-txt">{_txt}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            st.markdown('</div>', unsafe_allow_html=True)

    # ── Reddit page ──────────────────────────────────────────────────
    elif _current == "reddit":
        rA, rB = st.columns([1, 2])
        with rA:
            st.markdown("<h2>Reddit User Analysis</h2>", unsafe_allow_html=True)
            st.markdown('<p style="font-size:0.74rem;color:#6b7280">Fetches 6 months of posts and comments via the free Reddit API.</p>', unsafe_allow_html=True)
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            reddit_user = st.text_input("Username (without u/)", placeholder="e.g. spez", key="reddit_username")
            with st.expander("Reddit API credentials", expanded=True):
                st.markdown('<p style="font-size:0.7rem">Free at <a href="https://www.reddit.com/prefs/apps" target="_blank">reddit.com/prefs/apps</a> — create a script app.</p>', unsafe_allow_html=True)
                r_id     = st.text_input("Client ID",     value=os.getenv("REDDIT_CLIENT_ID", ""),     placeholder="under app name")
                r_secret = st.text_input("Client Secret", value=os.getenv("REDDIT_CLIENT_SECRET", ""), type="password")
            min_risk = st.slider("Show posts above risk score", 0.0, 1.0, 0.0, 0.05, key="r_min")
            n_show   = st.slider("Max posts to display", 5, 50, 20, 5, key="r_n")
            fetch_btn = st.button("Analyse Reddit User", use_container_width=True, key="reddit_fetch")
            if fetch_btn:
                if not reddit_user.strip(): st.warning("Enter a username.")
                elif not r_id or not r_secret: st.error("Enter your Reddit API credentials.")
                else:
                    uname = reddit_user.strip().lstrip("u/")
                    with st.spinner(f"Fetching posts for u/{uname}..."):
                        try:
                            raw = fetch_reddit(uname, r_id, r_secret)
                        except RuntimeError as e:
                            st.error(str(e)); raw = []
                    if raw:
                        with st.spinner(f"Running Mental-RoBERTa on {len(raw)} posts..."):
                            scores = predict_batch([clean_text(p["text"]) for p in raw])
                        df = pd.DataFrame(raw); df["risk_score"] = scores; df["date"] = pd.to_datetime(df["date"], utc=True)
                        st.session_state.reddit_results = {"username": uname, "df": df, "overall": float(np.percentile(scores, 85)), "n_high": int((scores >= 0.55).sum()), "signals": detect_socioeconomic(raw), "n_posts": len(raw), "min_risk": min_risk, "n_show": n_show}
                        st.rerun()
                    elif raw == []:
                        st.warning(f"No posts found for u/{reddit_user.strip()} in the last 6 months.")
        with rB:
            res = st.session_state.reddit_results
            if res is None:
                st.markdown('<div style="text-align:center;padding:4rem 1rem;color:#6b7280"><p>Enter a username and click Analyse Reddit User.</p></div>', unsafe_allow_html=True)
            else:
                df = res["df"]; st.markdown(f'<h3>u/{res["username"]}</h3>', unsafe_allow_html=True)
                overall_banner(res["overall"], res["n_posts"], res["n_high"], "6 months")
                st.markdown('<hr class="divider">', unsafe_allow_html=True)
                s1, s2, s3 = st.tabs(["Timeline", "Posts", "Socio-Economic"])
                with s1: st.plotly_chart(timeline_chart(df), use_container_width=True)
                with s2:
                    filtered = df[df["risk_score"] >= res["min_risk"]]
                    render_post_cards(filtered, sub_col="subreddit", url_col="url", type_col="type", n=res["n_show"])
                with s3: render_socio(res["signals"])

    # ── Video page ───────────────────────────────────────────────────
    elif _current == "video":
        vA, vB = st.columns([1, 1.4])
        with vA:
            st.markdown("<h2>Video Analysis</h2>", unsafe_allow_html=True)
            st.markdown('<p style="font-size:0.74rem;color:#6b7280">Paste any public video URL. Supports TikTok, Facebook, Instagram, Twitter/X, YouTube, Vimeo, Twitch, and 1000+ other sites.</p>', unsafe_allow_html=True)
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            video_url = st.text_input("Video URL", placeholder="https://www.tiktok.com/@user/video/...", key="video_url_input")
            st.markdown('<p style="font-size:0.7rem;color:#6b7280">Public videos only. First run downloads Whisper tiny model (~75MB).</p>', unsafe_allow_html=True)
            vid_btn = st.button("Transcribe and Analyse", use_container_width=True, key="video_analyse")
            if vid_btn:
                url = video_url.strip()
                if not url:
                    st.warning("Please paste a video URL.")
                else:
                    st.session_state.video_result = None
                    progress = st.progress(0); status = st.empty()
                    try:
                        with tempfile.TemporaryDirectory() as tmpdir:
                            status.markdown('<p style="font-size:0.76rem;color:#0F6E56">Downloading audio...</p>', unsafe_allow_html=True)
                            progress.progress(15)
                            audio_path = download_audio(url, tmpdir)
                            status.markdown('<p style="font-size:0.76rem;color:#0F6E56">Transcribing speech...</p>', unsafe_allow_html=True)
                            progress.progress(50)
                            transcript = transcribe_audio(audio_path)
                        progress.progress(75)
                        if not transcript.strip():
                            st.session_state.video_result = {"ok": False, "reason": "no_speech", "url": url}
                        else:
                            status.markdown('<p style="font-size:0.76rem;color:#0F6E56">Running Mental-RoBERTa...</p>', unsafe_allow_html=True)
                            prob, ms = predict_one(transcript)
                            progress.progress(100); status.empty()
                            st.session_state.video_result = {"ok": True, "url": url, "transcript": transcript, "prob": prob, "risk": prob, "ms": ms}
                            update_analytics(prob, transcript)
                    except RuntimeError as e:
                        progress.progress(100); status.empty()
                        st.session_state.video_result = {"ok": False, "reason": "error", "msg": str(e), "url": url}
                    st.rerun()
        with vB:
            vr = st.session_state.video_result
            if vr is None:
                st.markdown('<div style="text-align:center;padding:4rem 1rem;color:#6b7280"><p>Paste a video URL and click Transcribe and Analyse.</p><p style="font-size:0.72rem;margin-top:0.4rem">Supported: TikTok · Facebook · Instagram · Twitter/X · YouTube · Vimeo · Twitch · and more</p></div>', unsafe_allow_html=True)
            elif not vr.get("ok"):
                if vr.get("reason") == "no_speech":
                    st.warning("No speech detected. The video may be music-only or silent.")
                else:
                    st.error(f"{vr.get('msg', 'Download or transcription failed.')}")
                    st.markdown('<p style="font-size:0.72rem;color:#6b7280">Common causes: private video, region-locked, or URL expired.</p>', unsafe_allow_html=True)
            else:
                risk = vr["risk"]; prob = vr["prob"]; lbl, col, _ = risk_label(risk)
                st.markdown('<p class="section-label">Transcript</p>', unsafe_allow_html=True)
                st.markdown(f'<div style="background:#ffffff;border-radius:8px;padding:0.55rem 0.75rem;border:1px solid #d9e3df;font-size:0.76rem;line-height:1.6;color:#4b5563;max-height:150px;overflow-y:auto;">{vr["transcript"]}</div>', unsafe_allow_html=True)
                st.markdown('<hr class="divider">', unsafe_allow_html=True)
                st.markdown('<p class="section-label">Prediction</p>', unsafe_allow_html=True)
                r1, r2, r3 = st.columns(3)
                r1.metric("Risk Score", f"{risk:.1%}"); r2.metric("Risk Level", lbl); r3.metric("Latency", f"{vr['ms']:.0f}ms")
                st.plotly_chart(gauge(prob), use_container_width=True)
                if risk >= 0.55:   st.error("CRISIS ALERT — High-risk content detected.")
                elif risk >= 0.35: st.warning("Moderate risk detected.")
                else:              st.success("Low risk detected.")
                dl = f"Video URL: {vr['url']}\n\nTranscript:\n{vr['transcript']}\n\nRisk Score: {risk:.1%}\nRisk Level: {lbl}\nTimestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                st.download_button("Download report", dl, file_name="video_report.txt", use_container_width=True)
        vr2 = st.session_state.video_result
        if vr2 and vr2.get("ok"):
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            st.markdown('<p class="section-label">Socio-Economic Signals in Transcript</p>', unsafe_allow_html=True)
            render_socio(detect_socioeconomic([{"text": vr2["transcript"]}]))

    # ── Bluesky page ─────────────────────────────────────────────────
    elif _current == "bluesky":
        st.markdown("<h2>Bluesky Analysis</h2>", unsafe_allow_html=True)
        st.markdown('<p style="font-size:0.74rem;color:#6b7280">Fetches 3 months of posts for any public Bluesky account. Requires your Bluesky credentials.</p>', unsafe_allow_html=True)
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        bA, bB = st.columns([1, 2])
        with bA:
            st.text_input("Bluesky handle to analyse", placeholder="e.g. bsky.app", key="bsky_handle_input")
            st.markdown('<p class="section-label">Your credentials</p>', unsafe_allow_html=True)
            st.markdown('<p style="font-size:0.7rem;color:#6b7280">Bluesky Settings &rarr; Privacy &rarr; App Passwords &rarr; Add App Password</p>', unsafe_allow_html=True)
            st.text_input("Your Bluesky handle", placeholder="your.handle.bsky.social", key="bsky_identifier_input")
            st.text_input("App Password", type="password", placeholder="xxxx-xxxx-xxxx-xxxx", key="bsky_password_input")
            st.slider("Min risk score to display", 0.0, 1.0, 0.0, 0.05, key="bsky_min_input")
            st.slider("Max posts to display", 5, 50, 20, 5, key="bsky_n_input")
            if st.button("Analyse Bluesky User", use_container_width=True, key="bsky_go"):
                st.session_state["bsky_pending"] = {
                    "handle": st.session_state.get("bsky_handle_input", "").strip(),
                    "identifier": st.session_state.get("bsky_identifier_input", "").strip(),
                    "password": st.session_state.get("bsky_password_input", "").strip(),
                    "min_risk": st.session_state.get("bsky_min_input", 0.0),
                    "n_show":   st.session_state.get("bsky_n_input", 20),
                }
        pending = st.session_state.get("bsky_pending")
        if pending:
            st.session_state["bsky_pending"] = None
            handle = pending["handle"]; identifier = pending["identifier"]; password = pending["password"]
            if not handle: st.warning("Enter the Bluesky handle you want to analyse.")
            elif not identifier or not password: st.warning("Enter your Bluesky handle and App Password.")
            else:
                access_token = None; error_msg = None
                with st.spinner("Logging in to Bluesky..."):
                    try: access_token = bluesky_login(identifier, password)
                    except RuntimeError as e: error_msg = str(e)
                if error_msg:
                    st.error(f"Login failed: {error_msg}")
                else:
                    raw = []
                    with st.spinner(f"Fetching posts for {handle}..."):
                        try: raw = fetch_bluesky(handle, access_token=access_token)
                        except RuntimeError as e: error_msg = str(e)
                        except Exception as e: error_msg = f"Unexpected error: {e}"
                    if error_msg: st.error(f"Could not fetch posts: {error_msg}")
                    elif not raw: st.warning(f"No posts found for '{handle}' in the last 3 months.")
                    else:
                        with st.spinner(f"Running Mental-RoBERTa on {len(raw)} posts..."):
                            scores = predict_batch([clean_text(p["text"]) for p in raw])
                        df = pd.DataFrame(raw); df["risk_score"] = scores; df["date"] = pd.to_datetime(df["date"], utc=True)
                        st.session_state.bluesky_results = {"handle": handle, "df": df, "overall": float(np.percentile(scores, 85)), "n_high": int((scores >= 0.55).sum()), "signals": detect_socioeconomic(raw), "n_posts": len(raw), "min_risk": pending["min_risk"], "n_show": pending["n_show"]}
                        st.rerun()
        res = st.session_state.bluesky_results
        if res is None:
            with bB:
                st.markdown('<div style="text-align:center;padding:4rem 1rem;color:#6b7280"><p>Enter a handle and credentials, then click Analyse Bluesky User.</p></div>', unsafe_allow_html=True)
        else:
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            df = res["df"]; st.markdown(f'<h3>Results for {res["handle"]}</h3>', unsafe_allow_html=True)
            overall_banner(res["overall"], res["n_posts"], res["n_high"], "3 months")
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            s1, s2, s3 = st.tabs(["Timeline", "Posts", "Socio-Economic"])
            with s1: st.plotly_chart(timeline_chart(df), use_container_width=True)
            with s2:
                filtered = df[df["risk_score"] >= res["min_risk"]]
                render_post_cards(filtered, url_col="url", n=res["n_show"])
            with s3: render_socio(res["signals"])

    # ── Mastodon page ────────────────────────────────────────────────
    elif _current == "mastodon":
        mA, mB = st.columns([1, 2])
        with mA:
            st.markdown("<h2>Mastodon Analysis</h2>", unsafe_allow_html=True)
            st.markdown('<p style="font-size:0.74rem;color:#6b7280">Fetches 3 months of posts for any public Mastodon account. No API key needed.</p>', unsafe_allow_html=True)
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            mast_handle = st.text_input("Mastodon handle", placeholder="e.g. username@mastodon.social", key="mast_handle")
            mast_min = st.slider("Show posts above risk score", 0.0, 1.0, 0.0, 0.05, key="mast_min")
            mast_n   = st.slider("Max posts to display", 5, 50, 20, 5, key="mast_n")
            mast_btn = st.button("Analyse Mastodon User", use_container_width=True, key="mast_fetch")
            if mast_btn:
                handle = mast_handle.strip()
                if not handle: st.warning("Enter a Mastodon handle (format: username@instance.social).")
                else:
                    with st.spinner(f"Fetching posts for {handle}..."):
                        try: raw = fetch_mastodon(handle)
                        except RuntimeError as e: st.error(str(e)); raw = []
                    if raw:
                        with st.spinner(f"Running Mental-RoBERTa on {len(raw)} posts..."):
                            scores = predict_batch([clean_text(p["text"]) for p in raw])
                        df = pd.DataFrame(raw); df["risk_score"] = scores; df["date"] = pd.to_datetime(df["date"], utc=True)
                        st.session_state.mastodon_results = {"handle": handle, "df": df, "overall": float(np.percentile(scores, 85)), "n_high": int((scores >= 0.55).sum()), "signals": detect_socioeconomic(raw), "n_posts": len(raw), "min_risk": mast_min, "n_show": mast_n}
                        st.rerun()
                    elif raw == []: st.warning("No posts found or account is private/not found.")
        with mB:
            res = st.session_state.mastodon_results
            if res is None:
                st.markdown('<div style="text-align:center;padding:4rem 1rem;color:#6b7280"><p>Enter a handle and click Analyse Mastodon User.</p></div>', unsafe_allow_html=True)
            else:
                df = res["df"]; st.markdown(f'<h3>{res["handle"]}</h3>', unsafe_allow_html=True)
                overall_banner(res["overall"], res["n_posts"], res["n_high"], "3 months")
                st.markdown('<hr class="divider">', unsafe_allow_html=True)
                s1, s2, s3 = st.tabs(["Timeline", "Posts", "Socio-Economic"])
                with s1: st.plotly_chart(timeline_chart(df), use_container_width=True)
                with s2:
                    filtered = df[df["risk_score"] >= res["min_risk"]]
                    render_post_cards(filtered, url_col="url", n=res["n_show"])
                with s3: render_socio(res["signals"])

    # ── YouTube page ─────────────────────────────────────────────────
    elif _current == "youtube":
        yA, yB = st.columns([1, 2])
        with yA:
            st.markdown("<h2>YouTube Channel Analysis</h2>", unsafe_allow_html=True)
            st.markdown('<p style="font-size:0.74rem;color:#6b7280">Analyses video titles, descriptions, and top comments. Requires a free YouTube Data API v3 key.</p>', unsafe_allow_html=True)
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            yt_channel = st.text_input("YouTube channel URL or @handle", placeholder="https://youtube.com/@channelname", key="yt_channel")
            with st.expander("YouTube API key", expanded=True):
                st.markdown('<p style="font-size:0.7rem">Free at <a href="https://console.cloud.google.com" target="_blank">console.cloud.google.com</a> — enable YouTube Data API v3.</p>', unsafe_allow_html=True)
                yt_key = st.text_input("API Key", value=os.getenv("YOUTUBE_API_KEY", ""), type="password", key="yt_key")
            yt_min = st.slider("Show posts above risk score", 0.0, 1.0, 0.0, 0.05, key="yt_min")
            yt_n   = st.slider("Max items to display", 5, 50, 20, 5, key="yt_n")
            yt_btn = st.button("Analyse YouTube Channel", use_container_width=True, key="yt_fetch")
            if yt_btn:
                if not yt_channel.strip(): st.warning("Enter a channel URL or handle.")
                elif not yt_key: st.error("Enter your YouTube API key.")
                else:
                    with st.spinner("Fetching YouTube data..."):
                        try: raw = fetch_youtube(yt_channel.strip(), yt_key)
                        except RuntimeError as e: st.error(str(e)); raw = []
                    if raw:
                        with st.spinner(f"Running Mental-RoBERTa on {len(raw)} items..."):
                            scores = predict_batch([clean_text(p["text"]) for p in raw])
                        df = pd.DataFrame(raw); df["risk_score"] = scores; df["date"] = pd.to_datetime(df["date"], utc=True)
                        st.session_state.youtube_results = {"channel": yt_channel.strip(), "df": df, "overall": float(np.percentile(scores, 85)), "n_high": int((scores >= 0.55).sum()), "signals": detect_socioeconomic(raw), "n_posts": len(raw), "min_risk": yt_min, "n_show": yt_n}
                        st.rerun()
                    elif raw == []: st.warning("No content found in the last 3 months.")
        with yB:
            res = st.session_state.youtube_results
            if res is None:
                st.markdown('<div style="text-align:center;padding:4rem 1rem;color:#6b7280"><p>Enter a channel and click Analyse YouTube Channel.</p></div>', unsafe_allow_html=True)
            else:
                df = res["df"]; st.markdown(f'<h3>{res["channel"]}</h3>', unsafe_allow_html=True)
                overall_banner(res["overall"], res["n_posts"], res["n_high"], "3 months")
                st.markdown('<hr class="divider">', unsafe_allow_html=True)
                s1, s2, s3 = st.tabs(["Timeline", "Posts", "Socio-Economic"])
                with s1: st.plotly_chart(timeline_chart(df), use_container_width=True)
                with s2:
                    filtered = df[df["risk_score"] >= res["min_risk"]]
                    render_post_cards(filtered, url_col="url", n=res["n_show"])
                with s3: render_socio(res["signals"])

    # ── File Upload page ─────────────────────────────────────────────
    elif _current == "file":
        fA, fB = st.columns([1, 2])
        with fA:
            st.markdown("<h2>File Upload Analysis</h2>", unsafe_allow_html=True)
            st.markdown('<p style="font-size:0.74rem;color:#4b5563">Upload exported chat logs, journal entries, or any text file.</p>', unsafe_allow_html=True)
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            st.markdown('<p style="font-size:0.72rem;color:#6b7280">Accepted formats</p>', unsafe_allow_html=True)
            st.markdown('<ul style="font-size:0.72rem;color:#4b5563;padding-left:1.2rem"><li>.txt — WhatsApp export, journal, any plain text</li><li>.csv — exported tweets, posts, or any table with a text column</li><li>.json — Facebook data archive (posts_1.json) or Twitter/X archive (tweet.js)</li></ul>', unsafe_allow_html=True)
            uploaded = st.file_uploader("Upload file", type=["txt", "csv", "json"], label_visibility="collapsed")
            file_min = st.slider("Show entries above risk score", 0.0, 1.0, 0.0, 0.05, key="file_min")
            file_n   = st.slider("Max entries to display", 5, 100, 30, 5, key="file_n")
            file_btn = st.button("Analyse File", use_container_width=True, key="file_analyse")
            if file_btn:
                if not uploaded: st.warning("Please upload a file first.")
                else:
                    with st.spinner("Parsing file..."):
                        try: raw = parse_uploaded_file(uploaded)
                        except Exception as e: st.error(f"Could not parse file: {e}"); raw = []
                    if raw:
                        with st.spinner(f"Running Mental-RoBERTa on {len(raw)} entries..."):
                            scores = predict_batch([clean_text(p["text"]) for p in raw])
                        df = pd.DataFrame(raw); df["risk_score"] = scores; df["date"] = pd.to_datetime(df["date"], utc=True)
                        st.session_state.file_results = {"filename": uploaded.name, "df": df, "overall": float(np.percentile(scores, 85)), "n_high": int((scores >= 0.55).sum()), "signals": detect_socioeconomic(raw), "n_posts": len(raw), "min_risk": file_min, "n_show": file_n}
                        st.rerun()
                    elif raw == []: st.warning("No readable text found in the file.")
        with fB:
            res = st.session_state.file_results
            if res is None:
                st.markdown('<div style="text-align:center;padding:4rem 1rem;color:#6b7280"><p>Upload a file and click Analyse File.</p></div>', unsafe_allow_html=True)
            else:
                df = res["df"]; st.markdown(f'<h3>{res["filename"]}</h3>', unsafe_allow_html=True)
                overall_banner(res["overall"], res["n_posts"], res["n_high"], "file")
                st.markdown('<hr class="divider">', unsafe_allow_html=True)
                s1, s2, s3 = st.tabs(["Timeline", "Entries", "Socio-Economic"])
                with s1: st.plotly_chart(timeline_chart(df), use_container_width=True)
                with s2:
                    filtered = df[df["risk_score"] >= res["min_risk"]]
                    render_post_cards(filtered, n=res["n_show"])
                with s3: render_socio(res["signals"])

    # ── Facebook page ────────────────────────────────────────────────
    elif _current == "facebook":
        st.markdown("<h2>Facebook Public Profile Analysis</h2>", unsafe_allow_html=True)
        st.markdown('<p style="font-size:0.74rem;color:#6b7280">Scrapes public posts from a Facebook profile. Only works for profiles with public post visibility.</p>', unsafe_allow_html=True)
        st.markdown('<div style="background:#fffbeb;border-radius:8px;padding:0.45rem 0.7rem;border:1px solid #fde68a;margin-bottom:0.5rem"><p style="color:#92400e;font-size:0.74rem;margin:0">Only publicly visible posts are accessed. Research use under ethics approval TUM-SERC MSC/028/2025A.</p></div>', unsafe_allow_html=True)
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        fA2, fB2 = st.columns([1, 2])
        with fA2:
            st.text_input("Facebook profile URL", placeholder="https://www.facebook.com/username", key="fb_url_input")
            st.slider("Months to analyse", 1, 6, 3, 1, key="fb_months")
            st.slider("Show posts above risk score", 0.0, 1.0, 0.0, 0.05, key="fb_min")
            st.slider("Max posts to display", 5, 50, 20, 5, key="fb_n")
            if st.button("Scrape and Analyse", use_container_width=True, key="fb_go"):
                st.session_state["fb_triggered"] = True
        if st.session_state.get("fb_triggered"):
            fb_url_val = st.session_state.get("fb_url_input", "").strip()
            fb_mon_val = st.session_state.get("fb_months", 3)
            fb_min_val = st.session_state.get("fb_min", 0.0)
            fb_n_val   = st.session_state.get("fb_n", 20)
            st.session_state["fb_triggered"] = False
            if not fb_url_val: st.warning("Enter a Facebook profile URL.")
            elif "facebook.com" not in fb_url_val: st.warning("Enter a full Facebook URL e.g. https://www.facebook.com/username")
            else:
                raw = []; err_msg = None
                st.info(f"Headless browser starting — scraping {fb_url_val} ...")
                with st.spinner("This takes 30-60 seconds. Please wait..."):
                    try: raw = scrape_facebook_public(fb_url_val, months=fb_mon_val)
                    except RuntimeError as e: err_msg = str(e)
                    except Exception as e: err_msg = f"Unexpected error: {e}"
                if err_msg:
                    st.error(f"Scraping failed: {err_msg}")
                    st.markdown('<p style="font-size:0.74rem;color:#6b7280">Common causes: profile is private, Facebook blocked the request, or the URL is incorrect.</p>', unsafe_allow_html=True)
                elif not raw: st.warning("No public posts found. The profile may be private or Facebook blocked the request.")
                else:
                    with st.spinner(f"Running Mental-RoBERTa on {len(raw)} posts..."):
                        scores = predict_batch([clean_text(p["text"]) for p in raw])
                    df = pd.DataFrame(raw); df["risk_score"] = scores; df["date"] = pd.to_datetime(df["date"], utc=True)
                    st.session_state.facebook_results = {"url": fb_url_val, "df": df, "overall": float(np.percentile(scores, 85)), "n_high": int((scores >= 0.55).sum()), "signals": detect_socioeconomic(raw), "n_posts": len(raw), "min_risk": fb_min_val, "n_show": fb_n_val}
                    st.rerun()
        res = st.session_state.facebook_results
        if res is None:
            with fB2:
                st.markdown('<div style="text-align:center;padding:4rem 1rem;color:#6b7280"><p>Enter a public Facebook profile URL and click Scrape and Analyse.</p></div>', unsafe_allow_html=True)
        else:
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            st.markdown(f'<h3>Results for {res["url"]}</h3>', unsafe_allow_html=True)
            overall_banner(res["overall"], res["n_posts"], res["n_high"], "months")
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            s1, s2 = st.tabs(["Posts", "Socio-Economic"])
            with s1:
                filtered = res["df"][res["df"]["risk_score"] >= res["min_risk"]]
                render_post_cards(filtered, url_col="url", n=res["n_show"])
            with s2: render_socio(res["signals"])

    # ── Twitter / X page ─────────────────────────────────────────────
    elif _current == "twitter":
        st.markdown("<h2>Twitter / X Public Profile Analysis</h2>", unsafe_allow_html=True)
        st.markdown('<p style="font-size:0.74rem;color:#6b7280">Scrapes public tweets using a headless browser. Only works for public profiles.</p>', unsafe_allow_html=True)
        st.markdown('<div style="background:#fffbeb;border-radius:8px;padding:0.45rem 0.7rem;border:1px solid #fde68a;margin-bottom:0.5rem"><p style="color:#92400e;font-size:0.74rem;margin:0">Twitter/X increasingly requires login to view profiles. If scraping fails, use the File Upload tab with a Twitter data archive instead.</p></div>', unsafe_allow_html=True)
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        tA, tB = st.columns([1, 2])
        with tA:
            st.text_input("Twitter/X profile URL", placeholder="https://x.com/username", key="tw_url_input")
            st.slider("Show posts above risk score", 0.0, 1.0, 0.0, 0.05, key="tw_min")
            st.slider("Max posts to display", 5, 50, 20, 5, key="tw_n")
            if st.button("Scrape and Analyse", use_container_width=True, key="tw_go"):
                st.session_state["tw_triggered"] = True
        if st.session_state.get("tw_triggered"):
            tw_url_val = st.session_state.get("tw_url_input", "").strip()
            tw_min_val = st.session_state.get("tw_min", 0.0)
            tw_n_val   = st.session_state.get("tw_n", 20)
            st.session_state["tw_triggered"] = False
            if not tw_url_val: st.warning("Enter a Twitter/X profile URL.")
            elif "twitter.com" not in tw_url_val and "x.com" not in tw_url_val: st.warning("Enter a valid URL e.g. https://x.com/username")
            else:
                raw = []; err_msg = None
                st.info(f"Starting browser scrape of {tw_url_val}...")
                with st.spinner(f"Opening headless browser and scraping {tw_url_val}..."):
                    try: raw = scrape_twitter_public(tw_url_val)
                    except RuntimeError as e: err_msg = str(e)
                    except Exception as e: err_msg = f"Unexpected error: {e}"
                if err_msg:
                    st.error(f"Scraping failed: {err_msg}")
                    st.markdown('<p style="font-size:0.74rem;color:#6b7280">Twitter/X may require login. Use File Upload with a Twitter archive instead.</p>', unsafe_allow_html=True)
                elif not raw: st.warning("No tweets found. Profile may be private. Try File Upload with a Twitter archive.")
                else:
                    with st.spinner(f"Running Mental-RoBERTa on {len(raw)} tweets..."):
                        scores = predict_batch([clean_text(p["text"]) for p in raw])
                    df = pd.DataFrame(raw); df["risk_score"] = scores; df["date"] = pd.to_datetime(df["date"], utc=True)
                    st.session_state.twitter_results = {"url": tw_url_val, "df": df, "overall": float(np.percentile(scores, 85)), "n_high": int((scores >= 0.55).sum()), "signals": detect_socioeconomic(raw), "n_posts": len(raw), "min_risk": tw_min_val, "n_show": tw_n_val}
                    st.rerun()
        res = st.session_state.twitter_results
        if res is None:
            with tB:
                st.markdown('<div style="text-align:center;padding:4rem 1rem;color:#6b7280"><p>Enter a public Twitter/X URL and click Scrape and Analyse.</p><p style="font-size:0.72rem;margin-top:0.5rem">If login is required, use File Upload with a Twitter archive.</p></div>', unsafe_allow_html=True)
        else:
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            st.markdown(f'<h3>Results for {res["url"]}</h3>', unsafe_allow_html=True)
            overall_banner(res["overall"], res["n_posts"], res["n_high"], "3 months")
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            s1, s2 = st.tabs(["Posts", "Socio-Economic"])
            with s1:
                filtered = res["df"][res["df"]["risk_score"] >= res["min_risk"]]
                render_post_cards(filtered, url_col="url", n=res["n_show"])
            with s2: render_socio(res["signals"])

    # ── Multi-Platform page ──────────────────────────────────────────
    elif _current == "unified":
        st.markdown("<h2>Multi-Platform Unified Risk Profile</h2>", unsafe_allow_html=True)
        st.markdown('<p style="font-size:0.74rem;color:#6b7280">Combines results from all platforms you have already analysed in this session into one unified risk profile.</p>', unsafe_allow_html=True)
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        platform_results = {}
        if st.session_state.reddit_results:   platform_results["Reddit"]      = st.session_state.reddit_results
        if st.session_state.bluesky_results:  platform_results["Bluesky"]     = st.session_state.bluesky_results
        if st.session_state.mastodon_results: platform_results["Mastodon"]    = st.session_state.mastodon_results
        if st.session_state.youtube_results:  platform_results["YouTube"]     = st.session_state.youtube_results
        if st.session_state.file_results:     platform_results["File Upload"] = st.session_state.file_results
        if st.session_state.facebook_results: platform_results["Facebook"]    = st.session_state.facebook_results
        if st.session_state.twitter_results:  platform_results["Twitter/X"]   = st.session_state.twitter_results
        if st.session_state.video_result and st.session_state.video_result.get("ok"):
            vr = st.session_state.video_result
            platform_results["Video"] = {"overall": vr["risk"], "n_posts": 1, "n_high": 1 if vr["risk"] >= 0.55 else 0}
        if not platform_results:
            st.markdown('<div style="text-align:center;padding:3rem 1rem;color:#6b7280"><p>No platforms analysed yet. Go to each tab and run an analysis first.</p></div>', unsafe_allow_html=True)
        else:
            rows = []; all_scores = []
            for platform, res in platform_results.items():
                overall = res["overall"]; lbl, col, _ = risk_label(overall)
                rows.append({"Platform": platform, "Posts": res.get("n_posts", 1), "Overall Risk": f"{overall:.1%}", "High-Risk Posts": res.get("n_high", 0), "Risk Level": lbl})
                all_scores.append(overall)
            unified_score = float(np.mean(all_scores)); unified_lbl, unified_col, _ = risk_label(unified_score)
            u1, u2, u3 = st.columns(3)
            u1.metric("Unified Risk Score", f"{unified_score:.1%}")
            u2.metric("Platforms Analysed", str(len(platform_results)))
            u3.metric("Unified Risk Level", unified_lbl)
            st.markdown(f'<div style="display:inline-block;padding:5px 16px;border-radius:8px;background:{unified_col}22;color:{unified_col};border:1.5px solid {unified_col};font-weight:700;font-size:0.88rem;margin:4px 0">{unified_lbl} — Unified across {len(platform_results)} platform(s)</div>', unsafe_allow_html=True)
            if unified_score >= 0.55:
                st.error("CRISIS ALERT — Elevated risk detected across multiple platforms.")
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            st.markdown('<p class="section-label">Platform Breakdown</p>', unsafe_allow_html=True)
            fig = go.Figure()
            risk_vals = [float(r["Overall Risk"].rstrip("%")) / 100 for r in rows]
            bar_colors = ["#22c55e" if v < 0.35 else "#f59e0b" if v < 0.55 else "#f97316" if v < 0.75 else "#ef4444" for v in risk_vals]
            fig.add_bar(x=[r["Platform"] for r in rows], y=risk_vals, marker_color=bar_colors, text=[r["Overall Risk"] for r in rows], textposition="outside", textfont_color="#4b5563")
            fig.add_hline(y=unified_score, line_dash="dot", line_color="#0F6E56", annotation_text=f"Unified avg: {unified_score:.1%}", annotation_font_color="#0F6E56", annotation_font_size=10)
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#ffffff", font_color="#4b5563", yaxis=dict(tickformat=".0%", range=[0, 1.1], gridcolor="#e5e7eb", color="#4b5563"), xaxis=dict(color="#4b5563"), margin=dict(l=20, r=20, t=30, b=20), height=280, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
            st.markdown('<p class="section-label">Detail Table</p>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(rows).set_index("Platform"), use_container_width=True)
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            st.markdown('<p class="section-label">Combined Socio-Economic Signals</p>', unsafe_allow_html=True)
            combined_signals = {cat: [] for cat in SOCIOECONOMIC_KEYWORDS}
            for res in platform_results.values():
                if "signals" in res:
                    for cat, kws in res["signals"].items():
                        for item in kws:
                            if item not in combined_signals[cat]:
                                combined_signals[cat].append(item)
            render_socio(combined_signals)
            report_lines = [f"MindGuard Unified Risk Report\n{'='*40}\n", f"Unified Risk Score: {unified_score:.1%}  ({unified_lbl})\n", f"Platforms analysed: {', '.join(platform_results.keys())}\n\n"]
            for r in rows:
                report_lines.append(f"{r['Platform']}: {r['Overall Risk']} — {r['Risk Level']} ({r['Posts']} posts, {r['High-Risk Posts']} high-risk)\n")
            report_lines.append(f"\nTimestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            st.download_button("Download unified report", "".join(report_lines), file_name="mindguard_unified_report.txt", use_container_width=True)

    # ── Resources page ───────────────────────────────────────────────
    elif _current == "resources":
        st.markdown("<h2>Crisis Resources</h2>", unsafe_allow_html=True)
        st.markdown('<p style="font-size:0.74rem;color:#6b7280">Select your country or US state to see local crisis resources.</p>', unsafe_allow_html=True)
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        rc1, rc2 = st.columns([1, 1])
        with rc1:
            country_options = list(RESOURCES.keys()) + ["USA — Select a State"]
            selected_country = st.selectbox("Country / Region", country_options, key="res_region")
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            if selected_country == "USA — Select a State":
                selected_state = st.selectbox("Select your state", sorted(US_STATE_RESOURCES.keys()), key="res_state")
                st.markdown(f'<p class="section-label">Resources for {selected_state}</p>', unsafe_allow_html=True)
                st.markdown('<p style="font-size:0.72rem;font-weight:600;color:#6b7280;margin:0.3rem 0 0.15rem">National (available in all states)</p>', unsafe_allow_html=True)
                for r in RESOURCES["USA (National)"]:
                    render_resource_card(r, border_color="#0d9488")
                st.markdown(f'<p style="font-size:0.72rem;font-weight:600;color:#6b7280;margin:0.5rem 0 0.15rem">State-specific — {selected_state}</p>', unsafe_allow_html=True)
                for r in US_STATE_RESOURCES.get(selected_state, []):
                    render_resource_card(r, border_color="#7c3aed")
            else:
                render_resources(selected_country)
            st.markdown('<div style="margin-top:0.7rem;padding:0.5rem 0.65rem;background:#fef2f2;border-radius:8px;border:1px solid #fecaca"><p style="color:#991b1b;font-size:0.76rem;margin:0">If someone is in immediate danger, call emergency services immediately. MindGuard is a research tool — it does not replace clinical assessment.</p></div>', unsafe_allow_html=True)
        with rc2:
            st.markdown("<h2>About MindGuard</h2>", unsafe_allow_html=True)
            st.markdown(
                '<div style="font-size:0.76rem;line-height:1.85;color:#4b5563">'
                '<p class="section-label">What is MindGuard?</p>'
                '<p>MindGuard is a consent-first, human-in-the-loop clinical decision-support system designed to help trained mental health professionals identify early signals of suicidal ideation in consented digital text. It is not a diagnostic tool and does not replace clinical judgment — it surfaces meaningful signals earlier than traditional screening methods, giving counsellors and school psychologists a structured, evidence-based starting point for follow-up.</p>'
                '<p class="section-label">Model Architecture</p>'
                '<p>MindGuard is powered by Mental-RoBERTa (mental/mental-roberta-base), a transformer pre-trained on millions of mental health domain posts. The model was fine-tuned on 12,656 annotated posts using a stratified 75/10/15 train-validation-test split, achieving a ROC-AUC of 0.9813 and an accuracy of 92.5%, outperforming both a general RoBERTa baseline and a custom Bi-LSTM model.</p>'
                '<p class="section-label">Risk Tiers</p>'
                '<p>Low &lt;35% &nbsp;&middot;&nbsp; Moderate 35–55% &nbsp;&middot;&nbsp; High 55–75% &nbsp;&middot;&nbsp; Critical &gt;75%</p>'
                '<p class="section-label">How It Works</p>'
                '<p>Every output produced by MindGuard is reviewed by a qualified professional before any action is taken. No automated alerts are sent, no autonomous outreach occurs, and no data is stored between sessions.</p>'
                '</div>',
                unsafe_allow_html=True,
            )

    # ── Team page ────────────────────────────────────────────────────
    elif _current == "team":
        st.markdown("""
        <div class="team-hero">
            <div>
                <p class="section-label">MindGuard team</p>
                <h2>People behind the research workspace</h2>
                <p>Clinical care, model evaluation, data quality, and product engineering come together to keep each review grounded and useful.</p>
            </div>
            <div class="signed-in-chip">Research use only</div>
        </div>
        """, unsafe_allow_html=True)
        team_cols = st.columns(4)
        for i, member in enumerate(TEAM_MEMBERS):
            with team_cols[i % 4]:
                render_team_card(member)


# 9. Router
# Auth gate (section 5) already stopped unauthenticated users.
# Authenticated + terms-accepted sessions reach here and enter the main app.
if st.session_state["authenticated"] and st.session_state["terms_accepted"]:
    main_app()
