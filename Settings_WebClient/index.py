import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output

from app import app
from apps import QKD_settings, QKD_status
from navbar import Navbar


app.layout = html.Div([
    Navbar(),
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
    else:
       return QKD_status.serve_layout()

if __name__ == '__main__':
    app.run_server(debug='False', port='8080', host='127.0.0.1', use_reloader=False)