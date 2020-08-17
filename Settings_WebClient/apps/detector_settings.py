import dash_bootstrap_components as dbc
import dash_html_components as html
import dash_core_components as dcc
from dash.dependencies import Input, Output, State

from app import app

from S15lib.instruments import SinglePhotonDetector
import glob

dev_list = glob.glob('/dev/serial/by-id/*APD*')
photon_detectors = []
for dev in dev_list:
    photon_detectors.append(SinglePhotonDetector(f'/dev/serial/by-id/{dev_path}'))


########
def get_det_layout(detector):
    det_id = detector.identity
    return dbc.Card([dbc.CardHeader(html.H4(det_id)),
                     dbc.CardBody([
                         html.Div([html.Label('Bias Voltage', htmlFor=f'{det_id}_hvolt'),
                                   dcc.Input(id=f'{det_id}_hvolt', placeholder='0',
                                             type='number', min=0, max=90,
                                             value=detector.hvolt)
                                   ]),
                         html.Div([html.Label('Threshold voltage', htmlFor=f'{det_id}_threshvolt'),
                                   dcc.Input(id=f'{det_id}_threshvolt', placeholder='0',
                                             type='number', max=0, min=-0.1,
                                             value=detector.threshvolt)
                                   ])
                         # html.Div(children=['Temperature: ', html.Nobr(children=f'{detector.temperature}', id=f'{det_id}_temp')]),
                         # html.Div(children=['PID const P: ', html.Nobr(children='', id=f'{det_id}_constp')]),
                         # html.Div(children=['PID const I: ', html.Nobr(children='', id=f'{det_id}_consti')])
                     ])
                     ])


det_layouts = []
for detector in photon_detectors:
    det_layouts.append(get_det_layout(detector))


# used for loading data at the page load
hidden_field = html.Div('.', id='hidden-div-status', style={'display': 'none'})
dump_output_field = html.Div('.', id='dump', style={'display': 'none'})

# proc_status_interval = dcc.Interval(
#     id='proc_status_interval',
#     interval=1000,  # in milliseconds
#     n_intervals=0)

layout = dbc.Container([
    *[i for i in det_layouts],
    hidden_field,
    dump_output_field
])


def serve_layout():
    return layout


@app.callback([*[Output(f'{det.identity}_hvolt', 'children') for det in photon_detectors],
               *[Output(f'{det.identity}_threshvolt', 'children') for det in photon_detectors]],
              [Input("dump", "children")])
def load_det_info(n):
    return [det.hvolt for det in photon_detectors]
