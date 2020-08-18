import dash
import dash_bootstrap_components as dbc
import dash_html_components as html
import dash_core_components as dcc
from dash.dependencies import Input, Output, State

from app import app

from S15lib.instruments import SinglePhotonDetector, serial_connection
import glob



######## Layout for one detector
def create_det_layout(detector):
    det_id = detector.identity()
    return dbc.Card([dbc.CardHeader(html.H4(det_id)),
                     dbc.CardBody([
                        dbc.Row([dbc.Col(
                            html.Div([html.Label('Bias Voltage', htmlFor=f'{det_id}_hvolt'), 
                                   dcc.Input(id=f'{det_id}_hvolt', placeholder='0',
                                             type='number', min=0, max=100, step=0.1,
                                             value=detector.hvolt)
                                   ]), width=3),
                        dbc.Col(html.Div([html.Label('Threshold voltage', htmlFor=f'{det_id}_threshvolt'),
                                   dcc.Input(id=f'{det_id}_threshvolt', placeholder='0',
                                             type='number', max=0, min=-0.1, step=0.001,
                                             value=detector.threshvolt)
                                   ]),width=3),
                        dbc.Col(html.Div([html.Label('Detector temperature', htmlFor=f'{det_id}_temperature'),
                                   dcc.Input(id=f'{det_id}_temperature', placeholder='0',
                                             type='number', max=40, min=-50, step=1,
                                             value=detector.temperature)
                                   ]),width=3)
                         # html.Div(children=['Temperature: ', html.Nobr(children=f'{detector.temperature}', id=f'{det_id}_temp')]),
                         # html.Div(children=['PID const P: ', html.Nobr(children='', id=f'{det_id}_constp')]),
                         # html.Div(children=['PID const I: ', html.Nobr(children='', id=f'{det_id}_consti')])
                        ]),
                        html.P(),
                        html.Div([
                            dbc.Button(children='Get detector counts', color="success", id=f'{det_id}_counts_button'),
                            html.Label('', id=f'{det_id}_counts_label', style={'margin-left': 10})
                            ]),

                     ])])

def create_callbacks():
    global display_value
    try:
        display_value
    except:
        if det_dict:
            @app.callback(
                Output('hidden-div-det', 'children'),
                [*[Input(f'{det_id}_hvolt', 'value') for det_id in det_dict],
                 *[Input(f'{det_id}_threshvolt', 'value') for det_id in det_dict]])
            def display_value(*values):
                ctx = dash.callback_context
                trigger_id = ctx.triggered[0]['prop_id']
                trigger_id = trigger_id.rstrip('on').rstrip('value').rstrip('.')
                trigger_value = dash.callback_context.triggered[0]['value']
                if trigger_id  != '' and '_hvolt' in trigger_id:
                    det_dict[trigger_id.strip('_hvolt')].hvolt = trigger_value
                if trigger_id  != '' and '_threshvolt' in trigger_id:
                    det_dict[trigger_id.strip('_threshvolt')].threshvolt = trigger_value
                return f'{trigger_id}, {trigger_value}'


    for det_id in det_dict:
        if not det_id+"button_pressed" in globals():
            func_name = det_id+"button_pressed"
            globals()[det_id+"button_pressed"] = func_name
            def func_name(n):
                ctx = dash.callback_context
                trigger_id = ctx.triggered[0]['prop_id']
                trigger_id = trigger_id.rstrip('on').rstrip('value').rstrip('.')
                trigger_value = dash.callback_context.triggered[0]['value']
                if n is None:
                    # print('starting key gen')
                    return ''
                else:
                    # print(trigger_id)
                    detector = det_dict[trigger_id.strip('_counts_button.n_clicks')]
                    detector.time = 1000
                    counts = detector.counts()
                    return str(counts) + ' counts per second'
            app.callback(Output(f'{det_id}_counts_label', 'children'), [Input(f'{det_id}_counts_button', 'n_clicks')])(func_name)


dev_list = glob.glob('/dev/tty.*APD*')
if not dev_list:
    dev_list = glob.glob('/dev/serial/by-id/*APD*')
if not dev_list:
    dev_list = glob.glob('/dev/serial/by_id/*SPD*')
det_dict = {det.identity(): det for det in [SinglePhotonDetector(dev) for dev in dev_list]}
create_callbacks()  

def serve_layout():
    global dev_list, det_dict
    dev_list = glob.glob('/dev/tty.*APD*')
    det_dict = {det.identity(): det for det in [SinglePhotonDetector(dev) for dev in dev_list]}
    det_layouts = []
    for detector in det_dict:
        det_layouts.append(create_det_layout(det_dict[detector]))

    # used for loading data at the page load
    hidden_field_det = html.Div('.', id='hidden-div-det', style={'display': 'none'})
    layout = dbc.Container([
        *[i for i in det_layouts],
        hidden_field_det,
    ])
    if det_dict:
        create_callbacks()
    return layout
