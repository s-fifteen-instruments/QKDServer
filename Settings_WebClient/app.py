import dash
import dash_bootstrap_components as dbc

import S15qkd.controller as qkd_ctrl
qkd_ctrl.start_communication()

# app = dash.Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=[dbc.themes.BOOTSTRAP])
app = dash.Dash(__name__, suppress_callback_exceptions=True, title='S15 QKD', update_title=None)

server = app.server