import dash_bootstrap_components as dbc
from dash import html
from dash import dcc
import plotly.graph_objects as go
import numpy as np
# import dash_html_components as html
from dash.dependencies import Input, Output, State
from app import app

import S15qkd.controller as qkd_ctrl

# Maximum allowed QBER in percentage (for graphing)
MAX_ALLOWED_QBER = 12

def serve_layout():
    # Process status indicators
    # TODO(Justin): Possibly display process logs, see L49-118 commit b26055ab for partial implementation
    proc_style = {'padding-right': '20px'}
    proc_badge_style = {'color': 'secondary', 'className': 'mr-1'}
    col_width = 3

    transferd_status = html.Div([
        dbc.Badge(id='transferd_status', **proc_badge_style), 'transferd',
    ], style=proc_style)

    splicer_status = html.Div([
        dbc.Badge(id='splicer_status', **proc_badge_style), 'splicer',
    ], style=proc_style)

    readevents_status = html.Div([
        dbc.Badge(id='readevents_status', **proc_badge_style), 'readevents',
    ], style=proc_style)

    chopper_status = html.Div([
        dbc.Badge(id='chopper_status', **proc_badge_style), 'chopper',
    ], style=proc_style)

    chopper2_status = html.Div([
        dbc.Badge(id='chopper2_status', **proc_badge_style), 'chopper2',
    ],  style=proc_style)

    costream_status = html.Div([
        dbc.Badge(id='costream_status', **proc_badge_style), 'costream',
    ], style=proc_style)

    error_correction_status = html.Div([
        dbc.Badge(id='error_correction_status', **proc_badge_style), 'error correction',
    ], style=proc_style)

    processes_labels = dbc.Card([
        dbc.CardHeader(html.H4(f"Processes - {qkd_ctrl.identity}")),
        dbc.CardBody([
            dbc.Row([
                dbc.Col(transferd_status, width=col_width),
                dbc.Col(readevents_status, width=col_width),
                dbc.Col(chopper_status, width=col_width),
                dbc.Col(chopper2_status, width=col_width),
            ]),
            dbc.Row([
                dbc.Col(costream_status, width=col_width),
                dbc.Col(splicer_status, width=col_width),
                dbc.Col(error_correction_status, width=col_width),
            ]),
        ]),
    ])

    # Raw key generation status
    connection_status = html.Div(['Connection status: ', html.Nobr(id='connection_status')])
    symmetry_status = html.Div(['Symmetry: ', html.Nobr(id='symmetry')])
    protocol_status = html.Div(['Protocol: ', html.Nobr( id='protocol')])
    init_time_diff_status = html.Div(['Initial time difference: ', html.Nobr(id='init_time_diff')])
    tracked_time_diff_status = html.Div(['Tracked time difference: ', html.Nobr(id='tracked_time_diff')])
    received_epoch_status = html.Div(['Last received epoch: ', html.Nobr(id='last_received_epoch')])
    long_match_status = html.Div(['pfind long match (in sig): ', html.Nobr(id='sig_long')])
    short_match_status = html.Div(['pfind short match (in sig): ', html.Nobr(id='sig_short')])
    coincidences = html.Div(['Coincidences per epoch: ', html.Nobr(id='coincidences')])
    accidentals = html.Div(['Accidentals per epoch: ', html.Nobr(id='accidentals')])

    status_labels = dbc.Card([
        dbc.CardHeader(html.H4("Raw key generation")),
        dbc.CardBody([
            connection_status,
            symmetry_status,
            protocol_status,
            init_time_diff_status,
            tracked_time_diff_status,
            received_epoch_status,
            long_match_status,
            short_match_status,
            coincidences,
            accidentals,
        ]),
    ])

    # Error correction status
    total_ec_bits_status = html.Div(['Total error-corrected bits: ', html.Nobr(id='total_ec_key_bits')])
    start_epoch_status = html.Div(['Start epoch: ', html.Nobr(id='first_epoch')])
    num_epoch_status = html.Div(['Number of epochs: ', html.Nobr(id='undigested_epochs')])
    initial_qber_status = html.Div(['Initial quantum bit error: ', html.Nobr(id='init_QBER')])
    num_rawbits_status = html.Div(['Number of raw bits: ', html.Nobr(id='ec_raw_bits')])
    key_filename_status = html.Div(['Key file name: ', html.Nobr(id='key_file_name')])
    error_frac_status = html.Div(['Error fraction: ', html.Nobr(id='ec_err_fraction')])
    num_final_bits_status = html.Div(['Final number of error corrected bits: ', html.Nobr(id='ec_final_bits')])

    error_corr_labels = dbc.Card([
        dbc.CardHeader(html.H4('Error correction')),
        dbc.CardBody([
            total_ec_bits_status,
            html.P(),
            html.H5('Sent to error correction'),
            start_epoch_status,
            num_epoch_status,
            initial_qber_status,
            num_rawbits_status,
            html.P(),
            html.H5('From error correction'),
            key_filename_status,
            error_frac_status,
            num_final_bits_status,
        ]),
    ])

    # Start and stop key generation buttons
    start_key_gen_button = dbc.Button('Start key generation', color="success", id='start_raw_key_gen')
    kill_all_processes_button = dbc.Button('Stop all processes', color="danger", id='kill_all_processes')

    # Time interval between queries for presence of qcrypto processes
    proc_status_interval = dcc.Interval(
        id='proc_status_interval',
        interval=1000,  # in milliseconds
    )

    graph_qber = dcc.Graph(id='live-update-graph-qber')
    graph_final_bits = dcc.Graph(id='live-update-graph-bitrate')

    layout = dbc.Container([
        html.Div(id='hidden-div-1', style={'display': 'none'}),
        html.Div(id='hidden-div-2', style={'display': 'none'}),
        html.Br(),
        dbc.Row([
            dbc.Col([
                dbc.Row(start_key_gen_button),
                html.P(),
                dbc.Row(kill_all_processes_button),
            ], width=2),
            dbc.Col(processes_labels),
        ]),
        dbc.Row([
            dbc.Col(graph_qber),
            dbc.Col(graph_final_bits),
        ]),
        html.Br(),
        dbc.Row([
            dbc.Col(status_labels),
            dbc.Col(error_corr_labels),
        ]),
        html.Br(),
        proc_status_interval,
    ])
    return layout


@app.callback(
    Output('transferd-collapse', 'is_open'),
    [Input('transferd-collapse-button', 'n_clicks')],
    [State('transferd-collapse', 'is_open')],
)
def toggle_collapse(n, is_open):
    if n:
        return not is_open
    return False


process_list = [
    'transferd',
    'readevents',
    'chopper',
    'chopper2',
    'splicer',
    'costream',
    'error_correction',
]

@app.callback(
    [
        *[Output(proc+'_status', 'children') for proc in process_list],
        *[Output(proc+'_status', 'color') for proc in process_list],
    ],
    [Input('proc_status_interval', 'n_intervals')],
)
def load_process_states(value):
    proc_status_dict = {proc:'OFF' for proc in process_list}
    proc_color_dict = {proc:'danger' for proc in process_list}
    proc_dict = qkd_ctrl.get_process_states()
    for i in process_list:
        if proc_dict[i]:
            proc_status_dict[i] = 'ON'
            proc_color_dict[i] = 'success'
    return [*proc_status_dict.values(), *proc_color_dict.values()]


raw_keygen_info_list = [
    'connection_status',
    'symmetry',
    'protocol',
    'last_received_epoch',
    'init_time_diff',
    'sig_long',
    'sig_short',
    'tracked_time_diff',
    'coincidences',
    'accidentals',
]

@app.callback(
    [Output(info, 'children') for info in raw_keygen_info_list],
    [Input('proc_status_interval', 'n_intervals')],
)
def load_state_info(n):
    status_dct = dict(qkd_ctrl.get_status_info())  # copy values
    status_dct['symmetry'] = 'Low count side' if status_dct['symmetry'] else 'High count side'
    status_dct['protocol'] = 'BBM92' if status_dct['protocol'] == 1 else 'unknown'
    return [status_dct[info] for info in raw_keygen_info_list]


ec_info_list = [
    'total_ec_key_bits',
    'first_epoch',
    'undigested_epochs',
    'init_QBER',
    'ec_raw_bits',
    'key_file_name',
    'ec_err_fraction',
    'ec_final_bits',
]

@app.callback(
    [Output(info, 'children') for info in ec_info_list],
    [Input('proc_status_interval', 'n_intervals')],
)
def load_error_correction_info(n):
    ec_info_dct = qkd_ctrl.get_error_corr_info()
    return [ec_info_dct[info] for info in ec_info_list]


# Format for both axes in graph
graph_tickfont_format = {
    'family': 'Arial',
    'size': 16,
    'color': 'rgb(82, 82, 82)',
}
graph_axis_format = {
    'showline': True,
    'showgrid': False,
    'showticklabels': True,
    'linecolor': 'rgb(204, 204, 204)',
    'linewidth': 2,
    'ticks': 'inside',
    'range': [0, 1],  # to replace dynamically
    'tickfont': graph_tickfont_format,
}

@app.callback(
    Output('live-update-graph-qber', 'figure'),
    [Input('proc_status_interval', 'n_intervals')],
)
def update_graph_qber(n):
    y = np.array(list(qkd_ctrl.error_correction.ec_err_fraction_history)) * 100  # convert to percentage
    x = np.arange(0, len(y), 1)
    y_maxqber = np.ones(len(y)) * MAX_ALLOWED_QBER
    ylim = np.max(y) + 5 if len(y) > 0 else 1

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode='lines+markers', name='QBER'))
    fig.add_trace(go.Scatter(x=x, y=y_maxqber, mode='lines', name='Max. allowed QBER'))
    fig.update_layout(
        title='QBER history',
        xaxis_title=f'Last {len(x)} key generation runs',
        yaxis_title='Quantum bit error (%)',
        xaxis={**graph_axis_format, 'range': [0, len(x)-1]},
        yaxis={**graph_axis_format, 'range': [0, ylim]},
        legend=dict(
            orientation='h',
            yanchor='bottom', y=1.02,
            xanchor='right', x=1,
        ),
        plot_bgcolor='white',
    )
    return fig

@app.callback(
    Output('live-update-graph-bitrate', 'figure'),
    [Input('proc_status_interval', 'n_intervals')],
)
def update_graph_bitrate(n):
    y = np.array(list(qkd_ctrl.error_correction.ec_err_key_length_history))
    x = np.arange(0, len(y), 1)
    ylim = 1 if len(y) == 0 else np.ceil(np.max(y)/100)*100 + 5  # ensure upper bound (units of 100) is visible

    fig = go.Figure(data=go.Scatter(x=x, y=y, mode='lines+markers'))
    fig.update_layout(
        title='Key length generation history',
        xaxis_title=f'Last {len(x)} key generation runs',
        yaxis_title='Key length (bits)',
        xaxis={**graph_axis_format, 'range': [0, len(x)-1]},
        yaxis={**graph_axis_format, 'range': [0, ylim]},
        plot_bgcolor='white',
    )
    return fig


@app.callback(
    Output('hidden-div-1', 'children'),
    [Input('start_raw_key_gen', 'n_clicks')],
)
def on_button_click(n):
    if n is not None:
        print('starting key gen')
        qkd_ctrl.start_service_mode()
    return ''


@app.callback(
    Output('hidden-div-2', 'children'),
    [Input('transferd_status', 'n_clicks')],
)
def on_button_click_comm(n):
    if n is not None:
        print('starting transferd')
        qkd_ctrl.start_communication()
    return ''


@app.callback(
    Output('start_raw_key_gen', 'children'),
    [Input('kill_all_processes', 'n_clicks')],
)
def on_kill_button_click(n):
    if n is not None:
        qkd_ctrl.stop_key_gen()
    return 'Start key generation'
