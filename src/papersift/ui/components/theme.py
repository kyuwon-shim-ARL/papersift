"""Theme toggle component and CSS for dark/light mode."""

from dash import html, dcc


# CSS variable-based theming
THEME_CSS = """
:root {
    --bg-primary: #ffffff;
    --bg-secondary: #f8f9fa;
    --bg-card: #ffffff;
    --text-primary: #212529;
    --text-secondary: #6c757d;
    --border-color: #dee2e6;
    --accent: #007bff;
    --hover-bg: #e9ecef;
    --shadow: 0 1px 3px rgba(0,0,0,0.1);
}

[data-theme="dark"] {
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-card: #1c2128;
    --text-primary: #e6edf3;
    --text-secondary: #7d8590;
    --border-color: #30363d;
    --accent: #58a6ff;
    --hover-bg: #21262d;
    --shadow: 0 1px 3px rgba(0,0,0,0.5);
}

body {
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
    transition: background-color 0.3s ease, color 0.3s ease;
}

/* Sidebar */
.sidebar-container {
    background-color: var(--bg-secondary) !important;
    border-right: 1px solid var(--border-color) !important;
    color: var(--text-primary) !important;
}

/* Main content */
.main-content {
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
}

/* Detail panel / Chat panel */
#detail-panel, #chat-panel {
    background-color: var(--bg-card) !important;
    border-left: 1px solid var(--border-color) !important;
    color: var(--text-primary) !important;
}

/* Buttons - keep their own colors but adjust for dark mode */
.sidebar-container button {
    transition: opacity 0.2s ease, transform 0.1s ease;
}
.sidebar-container button:hover {
    opacity: 0.9;
    transform: translateY(-1px);
}
.sidebar-container button:active {
    transform: translateY(0);
}

/* Labels and headings */
.sidebar-container label,
.sidebar-container h3,
.sidebar-container h4 {
    color: var(--text-primary) !important;
}
.sidebar-container small,
.sidebar-container .text-muted {
    color: var(--text-secondary) !important;
}

/* Stats */
#stats-display p {
    color: var(--text-primary) !important;
}

/* Breadcrumb */
#breadcrumb-container {
    color: var(--text-primary) !important;
}
#breadcrumb-container button {
    color: var(--accent) !important;
}

/* History info */
#history-info {
    color: var(--text-secondary) !important;
}

/* Collapsible sections */
.sidebar-container details {
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 8px 12px;
    background-color: var(--bg-card);
    transition: all 0.2s ease;
}

.sidebar-container details:hover {
    border-color: var(--accent);
    box-shadow: var(--shadow);
}

.sidebar-container details[open] {
    background-color: var(--bg-primary);
}

.sidebar-container summary {
    user-select: none;
    outline: none;
}

.sidebar-container summary::-webkit-details-marker {
    color: var(--accent);
}

.sidebar-container details > div {
    margin-top: 10px;
}

/* Theme toggle button */
.theme-toggle {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    padding: 10px 14px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    width: 100%;
    transition: all 0.2s ease;
    font-weight: 500;
}
.theme-toggle:hover {
    background-color: var(--hover-bg);
    border-color: var(--accent);
    box-shadow: var(--shadow);
}
.theme-toggle:active {
    transform: scale(0.98);
}

/* Tab styling */
.tab-container .tab {
    color: var(--text-primary) !important;
    background-color: var(--bg-secondary) !important;
    border-color: var(--border-color) !important;
}
.tab-container .tab--selected {
    background-color: var(--bg-primary) !important;
    border-bottom-color: var(--bg-primary) !important;
}

/* Tabs component */
._dash-undo-redo {
    display: none !important;
}

.tabs {
    color: var(--text-primary);
}

.tab {
    background-color: var(--bg-secondary) !important;
    border-color: var(--border-color) !important;
    color: var(--text-secondary) !important;
}

.tab--selected {
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
    border-bottom-color: var(--bg-primary) !important;
}

/* Loading component */
._dash-loading {
    color: var(--accent) !important;
}

/* AG Grid dark theme */
[data-theme="dark"] .ag-theme-alpine {
    --ag-background-color: var(--bg-primary);
    --ag-header-background-color: var(--bg-secondary);
    --ag-odd-row-background-color: var(--bg-secondary);
    --ag-row-hover-color: var(--hover-bg);
    --ag-foreground-color: var(--text-primary);
    --ag-header-foreground-color: var(--text-primary);
    --ag-border-color: var(--border-color);
    --ag-secondary-border-color: var(--border-color);
}

/* Plotly charts dark mode */
[data-theme="dark"] .js-plotly-plot .plotly,
[data-theme="dark"] .js-plotly-plot .plotly .main-svg {
    background-color: var(--bg-primary) !important;
}
[data-theme="dark"] .js-plotly-plot .plotly .bg {
    fill: var(--bg-primary) !important;
}
[data-theme="dark"] .js-plotly-plot text {
    fill: var(--text-primary) !important;
}
[data-theme="dark"] .js-plotly-plot .gridlayer path {
    stroke: var(--border-color) !important;
}
[data-theme="dark"] .js-plotly-plot .zerolinelayer path {
    stroke: var(--border-color) !important;
}

/* Slider styling */
.rc-slider-track {
    background-color: var(--accent) !important;
}
.rc-slider-handle {
    border-color: var(--accent) !important;
}
.rc-slider-handle:hover {
    border-color: var(--accent) !important;
}

/* Input fields */
input, select, textarea {
    background-color: var(--bg-card) !important;
    color: var(--text-primary) !important;
    border-color: var(--border-color) !important;
}

/* Headings in main content */
.main-content h1, .main-content h2, .main-content h3, .main-content h4 {
    color: var(--text-primary) !important;
}

.main-content p {
    color: var(--text-secondary) !important;
}

/* Detail panel / Chat panel content */
#detail-panel h3, #detail-panel h4,
#chat-panel h3, #chat-panel h4,
#detail-view h3, #detail-view h4 {
    color: var(--text-primary) !important;
}
#detail-panel p, #detail-panel div,
#detail-view p, #detail-view div {
    color: var(--text-primary) !important;
}
"""


def create_theme_toggle() -> html.Div:
    """Create theme toggle button."""
    return html.Div([
        html.Label('Theme', style={'fontWeight': '500', 'marginBottom': '8px', 'display': 'block'}),
        html.Button(
            '🌙 Dark Mode',
            id='theme-toggle-btn',
            n_clicks=0,
            className='theme-toggle',
        ),
        dcc.Store(id='theme-store', storage_type='local', data='light'),
    ], style={'marginBottom': '20px'})


def get_theme_style_element():
    """
    Return the CSS style element for theming.

    Note: Dash doesn't support html.Style directly. Instead, we use
    a raw HTML injection approach via the _dash-app-content wrapper.
    The proper way would be to use assets/ folder, but for a single
    component this inline approach works.
    """
    # Create a hidden div that contains a style tag via dangerouslySetInnerHTML
    # This is a workaround since Dash doesn't have html.Style
    return dcc.Markdown(
        children=f'<style>{THEME_CSS}</style>',
        dangerously_allow_html=True,
        style={'display': 'none'}
    )
