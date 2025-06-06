import signal

import dash
import dash_bootstrap_components as dbc
import S15qkd.controller as qkd_ctrl
import time

# app = dash.Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=[dbc.themes.BOOTSTRAP])
app = dash.Dash(__name__, suppress_callback_exceptions=True, title='S15 QKD', update_title=None)

server = app.server

@app.server.route("/status_keygen")
def keygen_status():
    """
    Returns status code 200 if QKD server is generating keys and 404 otherwise.

    A simple indication of whether server is generating keys is by checking
    presence of error correction process.

    Note:
        Routed by internal Flask server, so that we can bypass Dash rendering.
    """
    status = qkd_ctrl.get_process_states()
    is_generating_keys = status['error_correction']
    if is_generating_keys:
        errc_info = qkd_ctrl.get_error_corr_info()
        ret = str(errc_info['ec_key_gen_rate'])
        status_code = 200
    else:
        status_code = 404
        ret = ""
    return ret, status_code

@app.server.route("/status_qkd")
def status_qkd():
    status = qkd_ctrl.get_process_states()
    is_running = status['costream'] or status['splicer']
    return "", 200 if is_running else 404

@app.server.route("/set_conn/<conn_id>")
def set_connection(conn_id):
    qkd_ctrl.reload_configuration(conn_id)
    return "", 204

@app.server.route("/start_keygen")
def start_keygen():
    """Starts key generation."""
    qkd_ctrl.start_service_mode()
    return "", 204

@app.server.route("/stop_keygen")
def stop_keygen():
    """Stops key generation."""
    qkd_ctrl.stop_key_gen()
    return "", 204

@app.server.route("/restart_transferd")
def restart_transferd():
    """Kills then restarts transferd."""
    qkd_ctrl.restart_transferd()
    return "", 204

@app.server.route("/restart_connection")
def restart_connection():
    """Kills then restarts connection, authd and transferd."""
    qkd_ctrl.restart_connection()
    return "", 204

@app.server.route("/status_data")
def status_data():
    """ Sends status data in json format of GUI information """
    process_state = qkd_ctrl.get_process_states()
    status_info = qkd_ctrl.get_status_info()
    errc_info = qkd_ctrl.get_error_corr_info()
    now = time.time()
    json_info = {
            'time' : now,
            'process_state' : process_state,
            'status_info' : status_info,
            'errc_info' : errc_info,
            }
    return json_info, 200

signal.signal(signal.SIGINT, lambda *_: qkd_ctrl.stop())
signal.signal(signal.SIGTERM, lambda *_: qkd_ctrl.stop())
