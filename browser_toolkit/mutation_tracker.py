"""
DOM Mutation tracking: captures newly added elements, removed elements,
and modified attributes during and after UserScript execution.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List
from playwright.sync_api import Page


@dataclass
class AddedNodeInfo:
    selector: str
    tag_name: str
    id: str
    class_name: str
    text_snippet: str
    html_snippet: str


@dataclass
class RemovedNodeInfo:
    tag_name: str
    id: str
    class_name: str


@dataclass
class AttributeMutationInfo:
    selector: str
    attribute_name: str
    old_value: str | None
    new_value: str | None


@dataclass
class DOMMutationReport:
    added_nodes: List[AddedNodeInfo] = field(default_factory=list)
    removed_nodes: List[RemovedNodeInfo] = field(default_factory=list)
    attribute_mutations: List[AttributeMutationInfo] = field(default_factory=list)

    @property
    def has_mutations(self) -> bool:
        return bool(self.added_nodes or self.removed_nodes or self.attribute_mutations)


JS_INIT_MUTATION_TRACKER = r"""
(() => {
    if (window.__dom_mutations_installed) return;
    window.__dom_mutations_installed = true;

    window.__dom_mutations = {
        addedNodes: [],
        removedNodes: [],
        attributeMutations: []
    };

    function getSelector(el) {
        if (!el || el.nodeType !== 1) return '';
        if (el.id) return '#' + el.id;
        let name = el.tagName.toLowerCase();
        let cls = '';
        if (typeof el.className === 'string' && el.className.trim()) {
            const firstClass = el.className.trim().split(/\s+/)[0];
            if (firstClass && !firstClass.includes(':') && !firstClass.includes('[')) {
                cls = '.' + CSS.escape(firstClass);
            }
        }
        let parent = el.parentElement;
        if (parent && parent !== document.body && parent !== document.documentElement) {
            let parentName = parent.tagName.toLowerCase();
            if (parent.id) {
                parentName = '#' + parent.id;
            } else if (typeof parent.className === 'string' && parent.className.trim()) {
                const pCls = parent.className.trim().split(/\s+/)[0];
                if (pCls && !pCls.includes(':') && !pCls.includes('[')) {
                    parentName += '.' + CSS.escape(pCls);
                }
            }
            return `${parentName} > ${name}${cls}`;
        }
        return `${name}${cls}`;
    }

    const observer = new MutationObserver((mutations) => {
        for (let i = 0; i < mutations.length; i++) {
            const m = mutations[i];
            if (m.type === 'childList') {
                for (let j = 0; j < m.addedNodes.length; j++) {
                    const node = m.addedNodes[j];
                    if (node.nodeType === 1) {
                        window.__dom_mutations.addedNodes.push({
                            selector: getSelector(node),
                            tagName: node.tagName.toLowerCase(),
                            id: node.id || '',
                            className: typeof node.className === 'string' ? node.className.slice(0, 80) : '',
                            text: (node.innerText || node.textContent || '').trim().slice(0, 60),
                            htmlSnippet: (node.outerHTML || '').slice(0, 100)
                        });
                    }
                }
                for (let j = 0; j < m.removedNodes.length; j++) {
                    const node = m.removedNodes[j];
                    if (node.nodeType === 1) {
                        window.__dom_mutations.removedNodes.push({
                            tagName: node.tagName.toLowerCase(),
                            id: node.id || '',
                            className: typeof node.className === 'string' ? node.className.slice(0, 80) : ''
                        });
                    }
                }
            } else if (m.type === 'attributes') {
                const target = m.target;
                if (target && target.nodeType === 1) {
                    window.__dom_mutations.attributeMutations.push({
                        selector: getSelector(target),
                        attributeName: m.attributeName,
                        oldValue: m.oldValue ? String(m.oldValue).slice(0, 60) : null,
                        newValue: target.getAttribute(m.attributeName) ? String(target.getAttribute(m.attributeName)).slice(0, 60) : null
                    });
                }
            }
        }
    });

    observer.observe(document.documentElement || document, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeOldValue: true
    });
    window.__dom_mutation_observer = observer;
})();
"""

JS_GET_MUTATIONS = r"""
() => {
    const raw = window.__dom_mutations || { addedNodes: [], removedNodes: [], attributeMutations: [] };
    // Deduplicate added nodes by selector
    const seen = new Set();
    const uniqueAdded = [];
    for (const item of raw.addedNodes) {
        const key = item.selector + '|' + item.text;
        if (!seen.has(key)) {
            seen.add(key);
            uniqueAdded.push(item);
        }
    }
    return {
        addedNodes: uniqueAdded.slice(0, 30),
        removedNodes: raw.removedNodes.slice(0, 20),
        attributeMutations: raw.attributeMutations.slice(0, 20)
    };
}
"""


def attach_mutation_tracker(page: Page) -> None:
    """Attaches mutation tracker to page or page init script."""
    page.add_init_script(JS_INIT_MUTATION_TRACKER)


def collect_dom_mutations(page: Page) -> DOMMutationReport:
    """Collects all tracked DOM mutations from page."""
    try:
        raw = page.evaluate(JS_GET_MUTATIONS)
    except Exception:
        return DOMMutationReport()

    added = [
        AddedNodeInfo(
            selector=item.get("selector", ""),
            tag_name=item.get("tagName", ""),
            id=item.get("id", ""),
            class_name=item.get("className", ""),
            text_snippet=item.get("text", ""),
            html_snippet=item.get("htmlSnippet", ""),
        )
        for item in raw.get("addedNodes", [])
    ]

    removed = [
        RemovedNodeInfo(
            tag_name=item.get("tagName", ""),
            id=item.get("id", ""),
            class_name=item.get("className", ""),
        )
        for item in raw.get("removedNodes", [])
    ]

    attrs = [
        AttributeMutationInfo(
            selector=item.get("selector", ""),
            attribute_name=item.get("attributeName", ""),
            old_value=item.get("oldValue"),
            new_value=item.get("newValue"),
        )
        for item in raw.get("attributeMutations", [])
    ]

    return DOMMutationReport(
        added_nodes=added,
        removed_nodes=removed,
        attribute_mutations=attrs,
    )
