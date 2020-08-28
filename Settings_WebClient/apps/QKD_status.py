import dash_bootstrap_components as dbc
import dash_html_components as html
import dash_core_components as dcc
import plotly.graph_objects as go
import numpy as np
# import dash_html_components as html
from dash.dependencies import Input, Output, State
from app import app

import S15qkd.controller as qkd_ctrl



### QBER plot
qber_display = html.Div(children=['Current quantum bit error: ', html.Nobr(children='---', id='qber')])
ber_display = html.Div(children=['Bit error: ', html.Nobr(children='---', id='ber')])
proc_style = {'padding-right':'20px'}

# process status indicators
transferd_status = html.Div([dbc.Badge(children="NA", color="secondary",
                                               className="mr-1",
                                               id='transferd_status'), 'transferd'], style=proc_style)

splicer_status = html.Div([dbc.Badge(children="NA", color="secondary",
                                             className="mr-1",
                                             id='splicer_status'), 'splicer'], style=proc_style)

readevents_status =html.Div([dbc.Badge(children="NA", color="secondary",
                                                className="mr-1",
                                                id='readevents_status'), 'readevents'], style=proc_style)

chopper_status = html.Div([dbc.Badge(children="NA", color="secondary",
                                     className="mr-1",
                                     id='chopper_status'), 'chopper'], style=proc_style)

chopper2_status = html.Div([dbc.Badge(children="NA", color="secondary",
                                      className="mr-1",
                                      id='chopper2_status'), 'chopper2'], 
                                      style=proc_style)

costream_status = html.Div([dbc.Badge(children="NA", color="secondary",
                                              className="mr-1",
                                              id='costream_status'), 'costream'], style=proc_style)
error_correction_status = html.Div([dbc.Badge(children="OFF", color="secondary",
                                                      className="mr-1",
                                                      id='error_correction_status'), 'error correction'], style=proc_style)


transferd_log = html.Div([
    dbc.Button(
        "Transferd log",
        id="transferd-collapse-button",
        className="mb-3",
        color="primary",
    ),
    dbc.Collapse(
        dbc.Card(html.Textarea('test')),
        id="transferd-collapse",
    ), ])

chopper_log = html.Div([
    dbc.Button(
        "chopper log",
        id="chopper-collapse-button",
        className="mb-3",
        color="primary",
    ),
    dbc.Collapse(
        dbc.Card(html.Textarea('chopper output')),
        id="chopper-collapse",
    ), ])

chopper2_log = html.Div([
    dbc.Button(
        "chopper2 log",
        id="chopper2-collapse-button",
        className="mb-3",
        color="primary",
    ),
    dbc.Collapse(
        dbc.Card(html.Textarea('chopper2 output')),
        id="chopper2-collapse",
    ), ])

splicer_log = html.Div([
    dbc.Button(
        "splicer log",
        id="splicer-collapse-button",
        className="mb-3",
        color="primary",
    ),
    dbc.Collapse(
        dbc.Card(html.Textarea('splicer output')),
        id="splicer-collapse")])

costream_log = html.Div([
    dbc.Button(
        "costream log",
        id="costream-collapse-button",
        className="mb-3",
        color="primary",
    ),
    dbc.Collapse(
        dbc.Card(html.Textarea('costream output')),
        id="costream-collapse")])


error_correction_log = html.Div([
    dbc.Button(
        "Error correction log",
        id="error_correction-collapse-button",
        className="mb-3",
        color="primary",
    ),
    dbc.Collapse(
        dbc.Card(html.Textarea('error_correction output')),
        id="error_correction-collapse",
    ), ])

col_width = 3
processes_row1 = dbc.Row([dbc.Col(transferd_status, width=col_width), 
                          dbc.Col(readevents_status, width=col_width), 
                          dbc.Col(chopper_status, width=col_width),
                          dbc.Col(chopper2_status, width=col_width)])
processes_row2 = dbc.Row([dbc.Col(costream_status, width=col_width), 
                          dbc.Col(splicer_status, width=col_width), 
                          dbc.Col(error_correction_status, width=col_width)])
    # dbc.Coltransferd_status, splicer_status, readevents_status,
                                    # chopper_status, html.P(),chopper2_status, costream_status,
                                    # error_correction_status, 
processes = dbc.Card([dbc.CardHeader(html.H4(f"Processes - {qkd_ctrl.identity}")),
                      dbc.CardBody([processes_row1, processes_row2])])



connection_status = html.Div(children=['Connection status: ', html.Nobr(children='---', id='connection_status')])
symmetry_status = html.Div(children=['Symmetry: ', html.Nobr(children='---', id='symmetry')])
protocol_status = html.Div(children=['Protocol: ', html.Nobr(children='---', id='protocol')])
tracked_time_diff_status = html.Div(children=['Tracked time difference: ', html.Nobr(children='---', id='tracked_time_diff')])
received_epoch_status = html.Div(children=['Last received epoch: ', html.Nobr(children='---', id='last_received_epoch')])
init_time_diff_status = html.Div(children=['Initial time difference: ', html.Nobr(children='---', id='init_time_diff')])
long_match_status = html.Div(children=['pfind long match (in sig): ', html.Nobr(children='---', id='sig_long')])
short_match_status = html.Div(children=['pfind short match (in sig): ', html.Nobr(children='---', id='sig_short')])
coincidences = html.Div(children=['coincidences per epoch: ', html.Nobr(children='---', id='coincidences')])
accidentals = html.Div(children=['accidentals per epoch: ', html.Nobr(children='---', id='accidentals')])


status_labels = dbc.Card([dbc.CardHeader(html.H4("Raw key generation")),
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
                          accidentals])
                          ])

start_epoch_status = html.Div(
    children='latest start epoch: ---', id='start_epoch_status')
epochs_status = html.Div(
    children='Number of epochs: ---', id='epochs_status')
raw_bits_status = html.Div(
    children='Raw bits: ---', id='raw_bits_status')

total_ec_bits = html.Div(children=['Total error-corrected bits: ', html.Nobr(children='', id='total_ec_key_bits')])

to_ec = [html.Div(children=['Start epoch: ', html.Nobr(children='', id='first_epoch')]),
         html.Div(children=['Number of epochs: ', html.Nobr(children='', id='undigested_epochs')]),
         html.Div(children=['Initial quantum bit error: ', html.Nobr(children='', id='init_QBER')]),
         html.Div(children=['Number of raw bits: ', html.Nobr(children='', id='ec_raw_bits')])]

from_ec = [html.Div(children=['Key file name: ', html.Nobr(children='', id='key_file_name')]),
           html.Div(children=['Error fraction: ', html.Nobr(children='', id='ec_err_fraction')]),
           html.Div(children=['Final number of error corrected bits: ', html.Nobr(children='', id='ec_final_bits')])]


error_corr_labels = dbc.Card([
    dbc.CardHeader(html.H4("Error correction")),
    dbc.CardBody([total_ec_bits, 
    html.H5('Sent to error correction', className="card-title"),
    *to_ec,
    html.P(), 
    html.H5('From error correction'), *from_ec])])

hidden_field = html.Div('.', id='hidden-div-status', style={'display': 'none'}) # used for loading data at the page load
dump_output_field = html.Div('.', id='dump', style={'display': 'none'}) # used for loading data at the page load
dump_output_field2 = html.Div('.', id='dump2', style={'display': 'none'}) # used for loading data at the page load

# Buttons
start_key_gen_button = dbc.Button(children='Start key generation',
                                  color="success", id='start_raw_key_gen')
kill_all_processes_button = dbc.Button(children='Stop all processes',
                                  color="danger", id='kill_all_processes')


proc_status_interval = dcc.Interval(
            id='proc_status_interval',
            interval=1000, # in milliseconds
            n_intervals=0)

graph_qber = dcc.Graph(id='live-update-graph-qber')
graph_final_bits = dcc.Graph(id='live-update-graph-bitrate')

def serve_layout():
    layout = dbc.Container(
        [hidden_field,
         html.Br(),
         dump_output_field,
         dump_output_field2,
         dbc.Row([
            dbc.Col([dbc.Row(start_key_gen_button), html.P(),
                     dbc.Row(kill_all_processes_button)], width=2),
            dbc.Col(processes)
         ]),
         dbc.Row([dbc.Col(graph_qber),
                  dbc.Col(graph_final_bits)]),
         html.Br(),
         dbc.Row([dbc.Col(status_labels), dbc.Col(error_corr_labels)]),
         html.Br(),
         proc_status_interval])
    return layout


@app.callback(
    Output("transferd-collapse", "is_open"),
    [Input("transferd-collapse-button", "n_clicks")],
    [State("transferd-collapse", "is_open")],
)
def toggle_collapse(n, is_open):
    if n:
        return not is_open
    return False


process_list = ['transferd', 'readevents',
                'chopper', 'chopper2', 'splicer',
                'costream', 'error_correction']
@app.callback(
    [*[Output(proc+'_status', 'children') for proc in process_list],
     *[Output(proc+'_status', "color") for proc in process_list]],
    [Input("proc_status_interval", "n_intervals")]
)
def load_process_states(value):
    proc_status_dict = {proc: 'OFF' for proc in process_list}
    proc_color_dict = {proc: 'danger' for proc in process_list}
    proc_dict = qkd_ctrl.get_process_states()
    for i in process_list:
        if proc_dict[i]:
            proc_status_dict[i] = 'ON'
            proc_color_dict[i] = 'success'
        else:
            proc_status_dict[i] = 'OFF'
            proc_color_dict[i] = 'danger'
    return [*proc_status_dict.values(), *proc_color_dict.values()]


@app.callback([Output('connection_status', 'children'),
               Output('symmetry', 'children'),
               Output('protocol', 'children'),
               Output('last_received_epoch', 'children'),
               Output('init_time_diff', 'children'),
               Output('sig_long', 'children'),
               Output('sig_short', 'children'),
               Output('tracked_time_diff', 'children'),
               Output('coincidences', 'children'),
               Output('accidentals', 'children'),
              ],
              [Input("proc_status_interval", "n_intervals")])
def load_state_info(n):
    status_dct = qkd_ctrl.get_status_info()

    if status_dct['symmetry'] is True:
        symmetry = 'Low count side'
    elif status_dct['symmetry'] is False:
        symmetry = 'High count side'
    else:
        symmetry = status_dct['symmetry']

    if status_dct['protocol'] == 1:
        protocol = 'BBM92'
    else:
        protocol = 'unknown'
    return [status_dct['connection_status'], symmetry,
            protocol, status_dct['last_received_epoch'],
            status_dct['init_time_diff'], status_dct['sig_long'],
            status_dct['sig_short'], status_dct['tracked_time_diff'],
            status_dct['coincidences'], status_dct['accidentals']]


ec_info_list = ['first_epoch', 'undigested_epochs',
                'ec_raw_bits', 'ec_final_bits', 'ec_err_fraction',
                'key_file_name', 'total_ec_key_bits', 'init_QBER']
@app.callback(
        [*[Output(info, 'children') for info in ec_info_list]],
        [Input("proc_status_interval", "n_intervals")])
def load_error_correction_info(n):
    ec_info_dct = qkd_ctrl.get_error_corr_info()
    return [ec_info_dct[info] for info in ec_info_list]


@app.callback(Output('live-update-graph-qber', 'figure'),
              [Input("proc_status_interval", "n_intervals")])
def update_graph_qber(n):
    y = np.array(list(qkd_ctrl.error_correction.ec_err_fraction_history)) * 100
    x = np.arange(0, len(y), 1)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode='lines+markers', name='QBER'))
    fig.add_trace(go.Scatter(x=x, y =np.ones(len(y))*12, mode='lines', name='Max. allowed QBER'))
    # if len(y) > 1:
    #     fig.add_trace(go.Scatter(x=[0, len(y)-1], y=[12, 12],
    #                     mode='line', line=dict(color='firebrick', width=4, dash='dash')))
    ylim = np.max(y) + 5 if len(y) > 0 else 1
    fig.update_layout(title='QBER history',
                   xaxis_title=f'Last {len(y)} key generation runs',
                   yaxis_title='Quantum bit error (%)',
                   xaxis=dict(
                            showline=True,
                            showgrid=False,
                            showticklabels=True,
                            linecolor='rgb(204, 204, 204)',
                            linewidth=2,
                            ticks='inside',
                            range=[0, len(x)-1],
                            tickfont=dict(
                                family='Arial',
                                size=16,
                                color='rgb(82, 82, 82)',
                                ),
                            ),
                   yaxis=dict(
                            showline=True,
                            showgrid=False,
                            zeroline=False,
                            showticklabels=True,
                            linecolor='rgb(230, 230, 230)',
                            linewidth=2,
                            range=[0, ylim],
                            ticks='inside',
                            tickfont=dict(
                                family='Arial',
                                size=16,
                                color='rgb(82, 82, 82)'),
                            ),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1),                   
                    plot_bgcolor='white',
                   )
    return fig

@app.callback(Output('live-update-graph-bitrate', 'figure'),
              [Input("proc_status_interval", "n_intervals")])
def update_graph_bitrate(n):
    y = np.array(list(qkd_ctrl.error_correction.ec_err_key_length_history))
    x = np.arange(0, len(y), 1)
    fig = go.Figure(data=go.Scatter(x=x, y=y, mode='lines+markers'))
    ylim = 1 if len(y) == 0 else np.ceil(np.max(y)/100)*100 + 5 
    fig.update_layout(title='Key length generation history',
                   xaxis_title=f'Last {len(y)} key generation runs',
                   yaxis_title='Key length (bits)',
                   xaxis=dict(
                            showline=True,
                            showgrid=False,
                            showticklabels=True,
                            linecolor='rgb(204, 204, 204)',
                            linewidth=2,
                            ticks='inside',
                            range=[0, len(y)-1],
                            tickfont=dict(
                                family='Arial',
                                size=16,
                                color='rgb(82, 82, 82)',
                                ),
                            ),
                   yaxis=dict(
                            showline=True,
                            showgrid=False,
                            showticklabels=True,
                            linecolor='rgb(204, 204, 204)',
                            linewidth=2,
                            range=[0, ylim],
                            ticks='inside',
                            tickfont=dict(
                                family='Arial',
                                size=16,
                                color='rgb(82, 82, 82)'),
                            ),
                   plot_bgcolor='white'
                   )
    return fig


@app.callback(Output('dump', 'children'),
    [Input("start_raw_key_gen", "n_clicks")])
def on_button_click(n):
    if n is not None:
        print('starting key gen')
        qkd_ctrl.start_key_generation()
    return ''

@app.callback(Output('dump2', 'children'),
    [Input("transferd_status", "n_clicks")])
def on_button_click(n):
    if n is not None:
        print('starting transferd')
        qkd_ctrl.start_communication()
    return ''

@app.callback(Output('start_raw_key_gen', 'children'),
    [Input("kill_all_processes", "n_clicks")]
)
def on_kill_button_click(n):
    if n is not None:
        qkd_ctrl.stop_all_processes()
    return 'Start key generation'
