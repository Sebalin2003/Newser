"""Interactive corpus search input built with Streamlit's v2 component API."""

from __future__ import annotations

import streamlit as st


_SEARCH_HTML = '<div id="newser-corpus-search" role="search"></div>'

_SEARCH_CSS = """
.search-shell { position: relative; font-family: var(--st-font, sans-serif); }
.search-row { align-items: center; background: var(--st-secondary-background-color, #111827); border: 1px solid var(--st-border-color, #334155); border-radius: 6px; display: flex; }
.search-row:focus-within { border-color: var(--st-primary-color, #2F6FED); }
.search-input { background: transparent; border: 0; color: var(--st-text-color, #E5E7EB); font: inherit; min-width: 0; outline: 0; padding: 0.62rem 0.75rem; width: 100%; }
.search-input::placeholder { color: var(--st-text-color, #94A3B8); opacity: 0.7; }
.clear-button { background: transparent; border: 0; color: var(--st-text-color, #E5E7EB); cursor: pointer; font-size: 1.25rem; line-height: 1; padding: 0.45rem 0.7rem; }
.clear-button[hidden] { display: none; }
.suggestions { background: var(--st-secondary-background-color, #111827); border: 1px solid var(--st-border-color, #334155); border-radius: 6px; margin-top: 0.35rem; overflow: hidden; }
.suggestion { align-items: center; background: transparent; border: 0; color: var(--st-text-color, #E5E7EB); cursor: pointer; display: grid; gap: 0.15rem 0.75rem; grid-template-columns: 1fr auto; padding: 0.55rem 0.75rem; text-align: left; width: 100%; }
.suggestion:hover, .suggestion[aria-selected="true"] { background: var(--st-primary-color, #2F6FED); color: white; }
.suggestion-title { font-size: 0.9rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.suggestion-meta { font-size: 0.78rem; grid-column: 1 / -1; opacity: 0.78; }
.suggestion-score { font-size: 0.82rem; font-variant-numeric: tabular-nums; }
"""

_SEARCH_JS = """
export default function(component) {
    const { data = {}, parentElement, setStateValue, setTriggerValue } = component;
    let root = parentElement.querySelector('#newser-corpus-search');
    if (!root) {
        root = document.createElement('div');
        root.id = 'newser-corpus-search';
        parentElement.appendChild(root);
    }

    let shell = root.querySelector('.search-shell');
    if (!shell) {
        shell = document.createElement('div');
        shell.className = 'search-shell';
        shell.innerHTML = '<div class="search-row"><input class="search-input" type="text" autocomplete="off" aria-label="Buscar en el corpus" placeholder="Buscar en títulos, descripciones y resúmenes..."><button class="clear-button" type="button" aria-label="Limpiar búsqueda" title="Limpiar búsqueda">×</button></div><div class="suggestions" role="listbox" hidden></div>';
        root.appendChild(shell);
    }

    const input = shell.querySelector('.search-input');
    const clear = shell.querySelector('.clear-button');
    const list = shell.querySelector('.suggestions');
    const draft = typeof data.draft === 'string' ? data.draft : '';
    const suggestions = Array.isArray(data.suggestions) ? data.suggestions : [];
    let activeIndex = Number(root.dataset.activeIndex || -1);

    if (document.activeElement !== input && input.value !== draft) {
        input.value = draft;
    }
    if (data.focusInput) {
        window.requestAnimationFrame(() => input.focus());
    }
    clear.hidden = !draft;

    const setActive = (index) => {
        const buttons = list.querySelectorAll('.suggestion');
        activeIndex = index;
        root.dataset.activeIndex = String(index);
        buttons.forEach((button, buttonIndex) => {
            button.setAttribute('aria-selected', String(buttonIndex === activeIndex));
        });
    };

    const choose = (item) => {
        input.value = item.title;
        setStateValue('draft', item.title);
    };

    list.replaceChildren();
    if (data.showSuggestions && suggestions.length) {
        list.hidden = false;
        suggestions.forEach((item, index) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'suggestion';
            button.setAttribute('role', 'option');
            button.setAttribute('aria-selected', String(index === activeIndex));

            const title = document.createElement('span');
            title.className = 'suggestion-title';
            title.textContent = item.title;
            const score = document.createElement('span');
            score.className = 'suggestion-score';
            score.textContent = `Score ${Math.round(item.score || 0)}`;
            const meta = document.createElement('span');
            meta.className = 'suggestion-meta';
            meta.textContent = `${item.source} · ${item.freshness}`;

            button.append(title, score, meta);
            button.onclick = () => choose(item);
            list.appendChild(button);
        });
    } else {
        list.hidden = true;
        activeIndex = -1;
        root.dataset.activeIndex = '-1';
    }

    input.oninput = () => {
        window.clearTimeout(root._searchTimer);
        root._searchTimer = window.setTimeout(() => {
            setStateValue('draft', input.value.trim());
        }, 250);
    };

    input.onkeydown = (event) => {
        if (event.key === 'ArrowDown' && suggestions.length) {
            event.preventDefault();
            setActive(Math.min(activeIndex + 1, suggestions.length - 1));
        } else if (event.key === 'ArrowUp' && suggestions.length) {
            event.preventDefault();
            setActive(Math.max(activeIndex - 1, 0));
        } else if (event.key === 'Enter') {
            event.preventDefault();
            const selected = suggestions[activeIndex];
            const query = (selected ? selected.title : input.value).trim();
            if (query) {
                setStateValue('draft', query);
                setTriggerValue('submit', query);
            }
        } else if (event.key === 'Escape' && input.value) {
            event.preventDefault();
            input.value = '';
            setStateValue('draft', '');
            setTriggerValue('clear', true);
        }
    };

    clear.onclick = () => {
        input.value = '';
        setStateValue('draft', '');
        setTriggerValue('clear', true);
    };
}
"""

_CORPUS_SEARCH = st.components.v2.component(
    "corpus_search",
    html=_SEARCH_HTML,
    css=_SEARCH_CSS,
    js=_SEARCH_JS,
)


def render_corpus_search(data: dict) -> object:
    return _CORPUS_SEARCH(
        key="corpus_search",
        data=data,
        default={"draft": ""},
        on_draft_change=lambda: None,
        on_submit_change=lambda: None,
        on_clear_change=lambda: None,
    )
