import dash_bootstrap_components as dbc
import dash_html_components as html
from dash.dependencies import Input, Output, State

from app import app


def Navbar():
  S15_logo = '/assets/img/s15-logo.png'
  nav = dbc.Navbar(
      [dbc.Row([
          dbc.Col(html.Img(src=S15_logo, height="70px")),
          dbc.Col(dbc.NavLink(
              "Status", className="ml-2", href="/apps/QKD_status", active=True)),
          dbc.Col(dbc.NavLink(
              "QKD settings", className="ml-2", href="/apps/QKD_settings", active=True)),
          # dbc.Col(dbc.NavLink(
          #     "Detectors", className="ml-2", href="/apps/detector_settings", active=True)),
          ],
          align="center",
          no_gutters=True,
      ),

          dbc.NavbarToggler(id="navbar-toggler"),
      ],
      sticky='top'
  )
  return nav
