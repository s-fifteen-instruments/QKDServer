import dash
from dash import dcc
import dash import html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import dash_daq as daq
import json
import re

from app import app
from S15qkd.qkd_globals import config_file


def serve_layout():
    debounce = True
    with open(config_file, 'r') as f:
        config = json.load(f)

    # # network connection settings
    identity = dcc.Input(id="identity",
                                type='text',
                                value=config['identity'])
    target_ip_input = dcc.Input(id="target_ip",
                                type='text',
                                value=config['target_ip'])
    port_num_input = dcc.Input(id="port_num", type='number',
                                value=config['port_num'])

    # peak finder and tracking
    pfind_epochs = dcc.Input(id="pfind_epochs", placeholder='5',
                             type='number', min=1, max=20,
                             value=config['pfind_epochs'])
    remote_coincidence_window = dcc.Input(id="remote_coincidence_window", placeholder='16',
                                          type='number', min=1, max=16,
                                          value=config["remote_coincidence_window"])
    tracking_window = dcc.Input(id="tracking_window", placeholder='30',
                                type='number', min=10, max=100,
                                value=config['tracking_window'])
    track_filter_time_constant = dcc.Input(id="track_filter_time_constant",
                                              placeholder='2000000', 
                                              type='number',
                                              value=config['track_filter_time_constant'])
    FFT_buffer_order = dcc.Input(id="FFT_buffer_order", placeholder=21,
                                 type='number', min=19, max=26,
                                 value=config['FFT_buffer_order'])
    # detector timing corrections
    det1corr = dcc.Input(id="det1corr", placeholder='0',
                         type='number',
                         value=config["local_detector_skew_correction"]['det1corr'])
    det2corr = dcc.Input(id="det2corr", placeholder='0',
                         type='number',
                         value=config["local_detector_skew_correction"]['det2corr'])
    det3corr = dcc.Input(id="det3corr", placeholder='0',
                         type='number',
                         value=config["local_detector_skew_correction"]['det3corr'])
    det4corr = dcc.Input(id="det4corr", placeholder='0',
                         type='number',
                         value=config["local_detector_skew_correction"]['det4corr'])

    # # error correction settings
    minimal_block_size = dcc.Input(id="minimal_block_size", placeholder='5000',
                                   type='number',
                                   value=config['minimal_block_size'])
    target_bit_error = dcc.Input(id="target_bit_error", placeholder='1E-9',
                                    type='number',
                                    value=config['target_bit_error'])

    # # protocol_choice = dcc.RadioItems(id='protocol'
    # #     options=[
    # #         {'label': ' BBM92    ', 'value': 1},
    # #         {'label': ' Service (not implemented yet)',
    # #          'value': 0, 'disabled': True}
    # #     ],
    # #     value=config['protocol'])

    clock_choice = dcc.RadioItems(id='clock_source',
                                  options=[
                                      {'label': ' external', 'value': '-e'},
                                      {'label': ' internal', 'value': ''}],
                                  value=config['clock_source'],
                                  labelStyle={'display': 'block'})

    error_corr_switch = daq.BooleanSwitch(
        id='error_correction',
        on=config['error_correction'],
        style={'display': 'inline-block'},
        color='#13c26d')

    privacy_ampl_switch = daq.BooleanSwitch(
        id='privacy_amplification',
        on=config['privacy_amplification'],
        style={'display': 'inline-block'},
        color='#13c26d')

    layout = dbc.Container([
        html.Div(id='hidden-div', style={'display': 'none'}),  # used for memory
        html.H1('QKD settings'),
        html.H4('Network connection settings'),
        dbc.Row([dbc.Col(html.Div([html.Label('Identity', htmlFor='identity'), identity]), width=3),
                dbc.Col(html.Div([html.Label('Target IP', htmlFor='target_ip'), target_ip_input]), width=3),
                dbc.Col(html.Div([html.Label('Port number', htmlFor='port_num'), port_num_input]), width=3)],
                justify="start"),

        html.Br(),
        html.H4('Clock source'),
        dbc.Row(dbc.Col(clock_choice, width=4)),
        html.Br(),
        html.H4('Peak finder & tracking settings'),
        dbc.Row([dbc.Col([html.Div([html.Label('Number of epochs for pfind ', htmlFor='pfind_epochs'), pfind_epochs]), html.P(),
                         html.Div([html.Label('Time bin width (1/8 ns)', htmlFor='remote_coincidence_window'), remote_coincidence_window])], width=3),
                dbc.Col([html.Div([html.Label('Tracking window (1/8 ns)', htmlFor='tracking_window'), html.Br(), tracking_window]), html.P(),
                         html.Div([html.Label('Tracking time filter constant (ns)', htmlFor='track_filter_time_constant'),track_filter_time_constant])], width=3),
                dbc.Col([html.Div([html.Label('FFT buffer order', htmlFor='FFT_buffer_order'), html.Br(), FFT_buffer_order])
                    ])]),
        html.Br(),
        html.H4('Detector correction settings (timing attack countermeasure)'),
        dbc.Row([
            dbc.Col([html.Div([html.Label('Detector 1 timing correction', htmlFor='det1corr'), det1corr]),html.P(),
                     html.Div([html.Label('Detector 3 timing correction', htmlFor='det3corr'), det3corr])], width=3),

            dbc.Col([html.Div([html.Label('Detector 2 timing correction', htmlFor='det2corr'), det2corr]),html.P(),
                     html.Div([html.Label('Detector 4 timing correction', htmlFor='det4corr'), det4corr])], width=3)]),

        html.Br(),
        html.H4('Error correction settings'),
        dbc.Row([
          dbc.Col([
            html.Br(),
            html.Div([error_corr_switch, ' Error correction']), 
            html.Br(),
            html.Div([privacy_ampl_switch, ' Privacy amplification'])], 
          width=3),
           html.Br(),
           dbc.Col([html.Div([html.Label('Minimal block size', htmlFor='minimal_block_size'), 
                    minimal_block_size]), 
                    html.P(),
                    html.Div([html.Label('Target bit error', htmlFor='target_bit_error'), target_bit_error])], width=3)
        ]),

        html.Div(html.Br())
    ])
    return layout
    # return target_ip_input


# Ugly!! need to keep this updated with the input fields.
property_list = ['target_ip', 'port_num',
                 'pfind_epochs', 'remote_coincidence_window',
                 'tracking_window', 'track_filter_time_constant',
                 'minimal_block_size', 'target_bit_error',
                 'det1corr', 'det2corr', 'det3corr', 'det4corr',
                 'clock_source', 'FFT_buffer_order', 'identity']
switch_settings_list = ['error_correction', 'privacy_amplification']

@app.callback(
    Output('hidden-div', 'children'),
    [*[Input(i, 'value') for i in property_list],
     *[Input(i, 'on') for i in switch_settings_list]])
def display_value(*values):
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]['prop_id']
    trigger_id = trigger_id.rstrip('on').rstrip('value').rstrip('.')
    trigger_value = dash.callback_context.triggered[0]['value']
    if trigger_id != '':
        with open(config_file, 'r') as f:
            config = json.load(f)
        if re.search('det\dcorr', trigger_id):
            config["local_detector_skew_correction"][trigger_id] = trigger_value
        else:
            config[trigger_id] = trigger_value
        json_config_writer(config)
    return f'{trigger_id}, {trigger_value}'


def json_config_writer(config):
    with open(config_file, 'w') as outfile:
        json.dump(config, outfile, indent=2)
