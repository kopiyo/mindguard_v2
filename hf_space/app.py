import os
import gradio as gr
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from huggingface_hub import hf_hub_download

BASE_MODEL = "roberta-base"
REPO_ID = "kopiyodiana/mindguard-mental-roberta"
WEIGHTS_FILE = "mindguard_best_weights.pt"
HF_TOKEN = os.environ.get("HF_TOKEN")

print("Loading tokenizer from base model...")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

print("Loading base model architecture...")
model = AutoModelForSequenceClassification.from_pretrained(
    BASE_MODEL, num_labels=2, ignore_mismatched_sizes=True
)

print(f"Downloading fine-tuned weights from {REPO_ID}...")
try:
    weights_path = hf_hub_download(
        repo_id=REPO_ID,
        filename=WEIGHTS_FILE,
        token=HF_TOKEN,
    )
    state = torch.load(weights_path, map_location="cpu", weights_only=True)
    model.load_state_dict(state, strict=False)
    print("Fine-tuned weights loaded.")
except Exception as e:
    print(f"Could not load fine-tuned weights ({e}), using base model.")

model.eval()
print("Model ready.")


def predict(texts: list) -> list:
    """Return P(suicidal) for each text in the input list."""
    if not texts:
        return []
    if isinstance(texts, str):
        texts = [texts]
    inputs = tokenizer(
        texts,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=256,
    )
    with torch.no_grad():
        outputs = model(**inputs)
    probs = torch.softmax(outputs.logits, dim=1)
    return probs[:, 1].tolist()


demo = gr.Interface(
    fn=predict,
    inputs=gr.JSON(label="texts"),
    outputs=gr.JSON(label="probabilities"),
    title="MindGuard Classifier",
    description="Pass a JSON list of strings; returns a list of suicidal-ideation probabilities.",
)

demo.launch()
