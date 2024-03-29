import dash_bootstrap_components as dbc
from dash import html
from dash.dependencies import Input, Output, State

from app import app


def Navbar():
  S15_logo = '/assets/img/s15-logo.png'
  nav = dbc.Navbar(
      [dbc.Row([
          dbc.Col(html.Img(src=S15_logo, height="70px")),
          dbc.Col(dbc.NavLink("Status", className="ml-2", href="/apps/QKD_status", active=True)),
          dbc.Col(dbc.NavLink("QKD Engine Settings", href="/apps/QKD_settings", active=True), width="auto"),
          dbc.Col(dbc.NavLink("Detectors", className="ml-2", href="/apps/detector_settings", active=True)),
          ],
          align="center",
          className="g-0",
      ),

          dbc.NavbarToggler(id="navbar-toggler"),
      ],
      sticky='top'
  )
  return nav
