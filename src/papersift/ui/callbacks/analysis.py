"""Analysis tab interactive callbacks for linked brushing."""

from dash import Input, Output, State, ctx, no_update, ALL


def register_analysis_callbacks(app):
    """Register all analysis-related callbacks."""

    # Hypothesis "Show Papers" button -> select supporting DOIs
    @app.callback(
        Output('selection-store', 'data', allow_duplicate=True),
        Input({'type': 'hyp-select-btn', 'index': ALL}, 'n_clicks'),
        State('analysis-hypotheses', 'data'),
        prevent_initial_call=True,
    )
    def hyp_select_papers(n_clicks_list, hypotheses_data):
        """Select papers supporting a hypothesis when button clicked."""
        if not any(n for n in n_clicks_list if n):
            return no_update

        if not hypotheses_data:
            return no_update

        triggered = ctx.triggered_id
        if not triggered:
            return no_update

        hyp_id = triggered['index']

        hypotheses = hypotheses_data.get('hypotheses', [])
        for h in hypotheses:
            if h.get('id') == hyp_id:
                dois = h.get('supporting_dois', [])
                if dois:
                    return {'selected_dois': dois, 'source': 'analysis'}

        return no_update
