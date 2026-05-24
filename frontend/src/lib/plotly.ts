import Plotly from 'plotly.js-dist-min'
import createPlotlyComponentModule from 'react-plotly.js/factory'

const createPlotlyComponent =
  (createPlotlyComponentModule as any).default ?? createPlotlyComponentModule

const Plot = createPlotlyComponent(Plotly)

export default Plot
