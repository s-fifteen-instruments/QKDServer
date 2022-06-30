import dash
import dash_bootstrap_components as dbc

import S15qkd.controller as qkd_ctrl
qkd_ctrl.start_communication()

# app = dash.Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=[dbc.themes.BOOTSTRAP])
app = dash.Dash(__name__, suppress_callback_exceptions=True, title='S15 QKD', update_title=None)

server = app.server

@app.server.route("/keygen_status")
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
    status_code = 200 if is_generating_keys else 404
    return "", status_code
