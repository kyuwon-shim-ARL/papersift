"""Theme toggle callbacks for dark/light mode switching."""

from dash import Input, Output, State


def register_theme_callbacks(app):
    """
    Register clientside callbacks for theme toggling.

    Uses clientside callbacks for instant switching without server roundtrip.
    Theme preference is persisted in localStorage via dcc.Store.
    """
    # Client-side callback for instant theme toggling
    app.clientside_callback(
        """
        function(n_clicks, current_theme) {
            if (n_clicks === 0) return window.dash_clientside.no_update;
            var newTheme = current_theme === 'dark' ? 'light' : 'dark';
            document.body.setAttribute('data-theme', newTheme);
            return newTheme;
        }
        """,
        Output('theme-store', 'data'),
        Input('theme-toggle-btn', 'n_clicks'),
        State('theme-store', 'data'),
        prevent_initial_call=True,
    )

    # Toggle table visibility
    app.clientside_callback(
        """
        function(n_clicks) {
            if (!n_clicks) return [window.dash_clientside.no_update, window.dash_clientside.no_update];
            var container = document.getElementById('table-container');
            var visible = container && container.style.display !== 'none';
            var newDisplay = visible ? 'none' : 'block';
            var label = visible ? 'Show Paper Table ▼' : 'Hide Paper Table ▲';
            return [{'display': newDisplay}, label];
        }
        """,
        Output('table-container', 'style'),
        Output('toggle-table-btn', 'children'),
        Input('toggle-table-btn', 'n_clicks'),
        prevent_initial_call=True,
    )

    # Update button text based on theme
    app.clientside_callback(
        """
        function(theme) {
            // Apply theme on page load (including initial)
            document.body.setAttribute('data-theme', theme || 'light');
            if (theme === 'dark') {
                return '☀️ Light Mode';
            }
            return '🌙 Dark Mode';
        }
        """,
        Output('theme-toggle-btn', 'children'),
        Input('theme-store', 'data'),
    )
