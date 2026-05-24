declare module 'react-plotly.js' {
  import { PlotParams } from 'plotly.js-dist-min'
  const Plot: React.ComponentType<PlotParams>
  export default Plot
}

declare module 'plotly.js-dist-min' {
  const Plotly: unknown
  export default Plotly
}

declare module 'react-plotly.js/factory' {
  import { PlotParams } from 'plotly.js-dist-min'

  export default function createPlotlyComponent(
    plotly: unknown
  ): React.ComponentType<PlotParams>
}
