# import dash_core_components as dcc
# import dash_html_components as html
from dash import dcc
from dash import html
from dash.dependencies import Input, Output
from importlib import reload

from app import app, server
from apps import QKD_settings, QKD_status, detector_settings
from navbar import Navbar


app.layout = html.Div([
    Navbar(),
    html.Title(id='dummy'),
    dcc.Location(id='url', refresh=False),
    html.Div(id='page-content')
])

@app.callback(Output('page-content', 'children'),
              [Input('url', 'pathname')])
def display_page(pathname):
    # print(pathname)
    if pathname == '/apps/QKD_settings':
        return QKD_settings.serve_layout()
    elif pathname == '/apps/QKD_status':
        return QKD_status.serve_layout()
    elif pathname == '/apps/detector_settings':
        return detector_settings.serve_layout()
    else:
       return QKD_status.serve_layout()

if __name__ == '__main__':
    app.run_server(debug=True, port='8000', host='0.0.0.0', use_reloader=True)
