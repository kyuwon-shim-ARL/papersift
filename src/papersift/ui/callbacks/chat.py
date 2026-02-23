"""Callbacks for the chat panel with Claude CLI backend."""

import json
import subprocess
import shutil
from collections import Counter

from dash import Input, Output, State, no_update, html, ctx, callback


def _build_cluster_summary(papers, clusters, max_chars=2000):
    """Build a compact cluster summary for the system prompt."""
    if not papers or not clusters:
        return "No data loaded."

    # Count papers per cluster
    cluster_counts = Counter(clusters.values())
    n_clusters = len(cluster_counts)

    # Build per-cluster topic summaries
    lines = []
    for cid, count in sorted(cluster_counts.items(), key=lambda x: -x[1]):
        # Collect topics from papers in this cluster
        dois_in_cluster = [doi for doi, c in clusters.items() if str(c) == str(cid)]
        topic_counts = Counter()
        for doi in dois_in_cluster:
            paper = next((p for p in papers if p.get('doi') == doi), None)
            if paper:
                for t in paper.get('topics', []):
                    name = t.get('display_name', t) if isinstance(t, dict) else str(t)
                    topic_counts[name] += 1
        top_topics = [t for t, _ in topic_counts.most_common(3)]
        topic_str = ', '.join(top_topics) if top_topics else 'no topics'
        lines.append(f"  C{cid}: {count} papers ({topic_str})")

    summary = '\n'.join(lines)
    # Truncate if too long
    if len(summary) > max_chars:
        summary = summary[:max_chars] + '\n  ...(truncated)'

    return f"{len(papers)} papers in {n_clusters} clusters:\n{summary}"


def _render_messages(messages):
    """Render message list as styled HTML elements."""
    elements = []
    for msg in messages:
        role = msg.get('role', 'user')
        content = msg.get('content', '')

        if role == 'user':
            elements.append(html.Div(
                content,
                style={
                    'backgroundColor': 'var(--accent)',
                    'color': '#ffffff',
                    'padding': '8px 12px',
                    'borderRadius': '12px 12px 2px 12px',
                    'fontSize': '13px',
                    'lineHeight': '1.5',
                    'alignSelf': 'flex-end',
                    'maxWidth': '85%',
                    'wordBreak': 'break-word',
                    'whiteSpace': 'pre-wrap',
                },
            ))
        else:
            elements.append(html.Div(
                content,
                style={
                    'backgroundColor': 'var(--bg-secondary)',
                    'color': 'var(--text-primary)',
                    'padding': '8px 12px',
                    'borderRadius': '12px 12px 12px 2px',
                    'fontSize': '13px',
                    'lineHeight': '1.5',
                    'alignSelf': 'flex-start',
                    'maxWidth': '85%',
                    'wordBreak': 'break-word',
                    'whiteSpace': 'pre-wrap',
                },
            ))
    return elements


def _parse_actions(text):
    """Parse optional actions from response text.

    Returns (clean_text, actions_list).
    """
    separator = '---ACTIONS---'
    if separator not in text:
        return text.strip(), []

    parts = text.split(separator, 1)
    clean_text = parts[0].strip()
    actions_json = parts[1].strip()

    try:
        parsed = json.loads(actions_json)
        actions = parsed.get('actions', [])
    except (json.JSONDecodeError, AttributeError):
        actions = []

    return clean_text, actions


def register_chat_callbacks(app):
    """Register chat panel callbacks."""

    # Detect if background callback manager is available
    has_bg = getattr(app, '_background_manager', None) is not None or \
             getattr(app, 'server', None) is not None and \
             getattr(app, '_background_manager', None) is not None
    # Simpler check: try to see if manager is set
    has_bg = hasattr(app, '_background_manager') and app._background_manager is not None

    bg_kwargs = {}
    if has_bg:
        bg_kwargs['background'] = True
        bg_kwargs['running'] = [
            (Output('chat-submit-btn', 'disabled'), True, False),
            (Output('chat-loading', 'style'), {'display': 'block'}, {'display': 'none'}),
        ]

    # Callback 1: Submit chat message
    @callback(
        Output('chat-history', 'data'),
        Output('chat-messages', 'children'),
        Output('selection-store', 'data', allow_duplicate=True),
        Output('view-tabs', 'value', allow_duplicate=True),
        Input('chat-submit-btn', 'n_clicks'),
        State('chat-input', 'value'),
        State('chat-history', 'data'),
        State('papers-data', 'data'),
        State('cluster-data', 'data'),
        State('selection-store', 'data'),
        State('cluster-colors', 'data'),
        prevent_initial_call=True,
        **bg_kwargs,
    )
    def submit_chat(n_clicks, message, history, papers, clusters,
                    selection, colors):
        if not message or not message.strip():
            return no_update, no_update, no_update, no_update

        message = message.strip()
        papers = papers or []
        clusters = clusters or {}

        # Build context
        cluster_summary = _build_cluster_summary(papers, clusters)
        selected_dois = selection.get('selected_dois', []) if selection else []
        if selected_dois:
            selection_info = f"{len(selected_dois)} papers currently selected"
        else:
            selection_info = "No papers selected"

        system_prompt = (
            f"You are a research assistant analyzing a literature landscape.\n"
            f"Dataset: {len(papers)} papers.\n\n"
            f"Cluster summary:\n{cluster_summary}\n\n"
            f"Current selection: {selection_info}\n\n"
            f"When responding, you can optionally include actions to update the UI.\n"
            f"Format actions as JSON at the end of your response after a line "
            f"\"---ACTIONS---\":\n"
            f"{{\"actions\": [\n"
            f"  {{\"type\": \"select_cluster\", \"cluster_id\": 0}},\n"
            f"  {{\"type\": \"set_tab\", \"tab\": \"landscape-tab\"}}\n"
            f"]}}\n\n"
            f"Available actions:\n"
            f"- select_cluster: highlight all papers in a cluster\n"
            f"- set_tab: switch to \"network-tab\", \"landscape-tab\", or \"analysis-tab\"\n"
            f"Only include actions when the user's question clearly implies a visual action."
        )

        # Call Claude CLI
        response_text = _call_claude(system_prompt, message)

        # Parse actions
        clean_text, actions = _parse_actions(response_text)

        # Update history
        messages = list(history.get('messages', []))
        messages.append({'role': 'user', 'content': message})
        messages.append({'role': 'assistant', 'content': clean_text})
        new_history = {'messages': messages}

        # Render messages
        rendered = _render_messages(messages)

        # Process actions
        new_selection = no_update
        new_tab = no_update
        for action in actions:
            atype = action.get('type', '')
            if atype == 'select_cluster':
                cid = action.get('cluster_id')
                if cid is not None:
                    dois = [doi for doi, c in clusters.items()
                            if str(c) == str(cid)]
                    new_selection = {'selected_dois': dois, 'source': 'chat'}
            elif atype == 'set_tab':
                tab = action.get('tab', '')
                if tab in ('network-tab', 'landscape-tab', 'analysis-tab'):
                    new_tab = tab

        return new_history, rendered, new_selection, new_tab

    def _call_claude(system_prompt, message):
        """Call claude CLI subprocess. Handles missing CLI and timeouts."""
        if not shutil.which('claude'):
            return "Claude CLI not found. Please install it to use the chat feature."

        try:
            result = subprocess.run(
                ['claude', '-p', '--output-format', 'json',
                 '--system-prompt', system_prompt, message],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip() if result.stderr else 'Unknown error'
                return f"Error from Claude CLI: {stderr}"

            try:
                response = json.loads(result.stdout)
                return response.get('result', 'Sorry, I could not process your request.')
            except json.JSONDecodeError:
                # Fallback: raw stdout
                return result.stdout.strip() if result.stdout.strip() else (
                    'Sorry, I could not process your request.'
                )
        except subprocess.TimeoutExpired:
            return "Request timed out (30s limit). Please try a shorter question."
        except OSError as e:
            return f"Failed to run Claude CLI: {e}"

    # Callback 2: Toggle between chat and detail view
    @app.callback(
        Output('detail-view', 'style'),
        Output('chat-view', 'style'),
        Output('detail-title', 'children'),
        Output('detail-meta', 'children'),
        Output('detail-abstract', 'children'),
        Output('detail-cluster-info', 'children'),
        Output('chat-panel', 'style'),
        Input('paper-table', 'cellClicked'),
        Input('landscape-scatter', 'clickData'),
        Input('chat-back-btn', 'n_clicks'),
        Input('chat-close-btn', 'n_clicks'),
        State('papers-data', 'data'),
        State('cluster-data', 'data'),
        State('extractions-data', 'data'),
        State('chat-panel', 'style'),
        prevent_initial_call=True,
    )
    def toggle_detail_view(cell_clicked, landscape_click, back_clicks,
                           close_clicks, papers, clusters, extractions, panel_style):
        triggered = ctx.triggered_id

        panel_style = dict(panel_style) if panel_style else {}

        # Close panel entirely
        if triggered == 'chat-close-btn':
            panel_style['display'] = 'none'
            return (
                no_update, no_update,
                no_update, no_update, no_update, no_update,
                panel_style,
            )

        # Back to chat: hide detail, show chat
        if triggered == 'chat-back-btn':
            detail_style = {'display': 'none', 'padding': '15px', 'overflowY': 'auto', 'flex': '1'}
            chat_style = {
                'display': 'flex', 'flexDirection': 'column',
                'flex': '1', 'overflow': 'hidden',
            }
            return (
                detail_style, chat_style,
                no_update, no_update, no_update, no_update,
                no_update,
            )

        # Paper click: show detail view
        doi = None
        if triggered == 'paper-table' and cell_clicked:
            doi = cell_clicked.get('rowId')
        elif triggered == 'landscape-scatter' and landscape_click:
            points = landscape_click.get('points', [])
            if points and 'customdata' in points[0]:
                doi = points[0]['customdata']

        if not doi or not papers:
            return (no_update,) * 7

        paper = next((p for p in papers if p.get('doi') == doi), None)
        if not paper:
            return (no_update,) * 7

        # Build detail content
        title = paper.get('title', 'Untitled')

        year = paper.get('year', 'N/A')
        doi_link = html.A(
            doi, href=f'https://doi.org/{doi}', target='_blank',
            style={'color': 'var(--accent)', 'wordBreak': 'break-all'},
        )
        meta = [
            html.P([html.Strong('Year: '), str(year)]),
            html.P([html.Strong('DOI: '), doi_link]),
        ]

        abstract_text = paper.get('abstract', '')
        if abstract_text:
            abstract = [
                html.H4('Abstract', style={'marginTop': '10px', 'fontSize': '14px'}),
                html.P(abstract_text, style={
                    'fontSize': '13px', 'lineHeight': '1.5',
                    'color': 'var(--text-primary)', 'textAlign': 'justify',
                }),
            ]
        else:
            abstract = [
                html.P('No abstract available',
                       style={'color': 'var(--text-secondary)', 'fontStyle': 'italic'}),
            ]

        cluster_id = clusters.get(doi, 'N/A') if clusters else 'N/A'
        cluster_info = [
            html.P([html.Strong('Cluster: '), str(cluster_id)]),
        ]
        topics = paper.get('topics', [])
        if topics:
            topic_names = [
                t.get('display_name', t) if isinstance(t, dict) else str(t)
                for t in topics[:5]
            ]
            cluster_info.append(
                html.Div([
                    html.Strong('Topics: '),
                    html.Div([
                        html.Span(name, style={
                            'backgroundColor': 'var(--hover-bg)',
                            'padding': '2px 8px',
                            'borderRadius': '12px',
                            'margin': '2px',
                            'fontSize': '12px',
                            'display': 'inline-block',
                        }) for name in topic_names
                    ], style={'marginTop': '5px'}),
                ]),
            )

        # Add extraction data if available
        extraction = extractions.get(doi, {}) if extractions else {}
        if extraction and any(extraction.get(k) for k in ['problem', 'method', 'finding']):
            ext_info = []
            if extraction.get('problem'):
                ext_info.append(html.P([
                    html.Strong('Problem: '), extraction['problem']
                ], style={'marginTop': '8px'}))
            if extraction.get('method'):
                ext_info.append(html.P([
                    html.Strong('Method: '), extraction['method']
                ], style={'marginTop': '8px'}))
            if extraction.get('finding'):
                ext_info.append(html.P([
                    html.Strong('Finding: '), extraction['finding']
                ], style={'fontSize': '13px', 'lineHeight': '1.5', 'marginTop': '8px'}))
            cluster_info.append(html.Hr(style={'margin': '15px 0'}))
            cluster_info.append(html.H4('LLM Extraction', style={
                'marginTop': '10px', 'color': 'var(--accent)', 'fontSize': '16px'
            }))
            cluster_info.extend(ext_info)

        # Show panel and switch to detail view
        panel_style['display'] = 'flex'
        detail_style = {
            'display': 'block', 'padding': '15px',
            'overflowY': 'auto', 'flex': '1',
        }
        chat_style = {
            'display': 'none', 'flexDirection': 'column',
            'flex': '1', 'overflow': 'hidden',
        }

        return detail_style, chat_style, title, meta, abstract, cluster_info, panel_style

    # Callback 3: Update context info
    @app.callback(
        Output('chat-context-info', 'children'),
        Input('papers-data', 'data'),
        Input('selection-store', 'data'),
    )
    def update_context_info(papers, selection):
        total = len(papers) if papers else 0
        selected = len(selection.get('selected_dois', [])) if selection else 0
        parts = [f'Context: {total} papers']
        if selected > 0:
            parts.append(f'Selected: {selected}')
        return ' | '.join(parts)

    # Callback 4: Clear input after submit (clientside)
    app.clientside_callback(
        """
        function(n_clicks) {
            if (!n_clicks) return window.dash_clientside.no_update;
            // Small delay to let submit read the value first
            setTimeout(function() {
                var el = document.getElementById('chat-input');
                if (el) el.value = '';
            }, 100);
            return '';
        }
        """,
        Output('chat-input', 'value'),
        Input('chat-submit-btn', 'n_clicks'),
        prevent_initial_call=True,
    )

    # Callback 5: Toggle chat panel open from sidebar button (clientside)
    app.clientside_callback(
        """
        function(n_clicks) {
            if (!n_clicks) return window.dash_clientside.no_update;
            var panel = document.getElementById('chat-panel');
            if (!panel) return window.dash_clientside.no_update;
            var visible = panel.style.display === 'flex';
            if (visible) {
                return {'width': '380px', 'display': 'none', 'flexDirection': 'column',
                         'flexShrink': '0', 'backgroundColor': 'var(--bg-card)',
                         'borderLeft': '1px solid var(--border-color)', 'height': '100vh'};
            }
            return {'width': '380px', 'display': 'flex', 'flexDirection': 'column',
                     'flexShrink': '0', 'backgroundColor': 'var(--bg-card)',
                     'borderLeft': '1px solid var(--border-color)', 'height': '100vh'};
        }
        """,
        Output('chat-panel', 'style', allow_duplicate=True),
        Input('chat-toggle-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
