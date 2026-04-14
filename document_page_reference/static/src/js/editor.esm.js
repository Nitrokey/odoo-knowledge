import {Component, useEffect, useRef, xml} from "@odoo/owl";
import {htmlField} from "@web/views/fields/html/html_field";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

class DocumentPageReferenceField extends Component {
    static props = ["*"];
    static template = xml`<div t-ref="container" class="o_field_html"/>`;

    setup() {
        this.containerRef = useRef("container");
        this.orm = useService("orm");
        this.action = useService("action");

        useEffect(
            () => {
                const isDirty = this.props.record.isDirty;
                const formEl = this.containerRef.el?.closest(".o_form_view");
                if (!formEl) return;
                if (isDirty) {
                    formEl.classList.add("dpref_show_editor");
                } else {
                    formEl.classList.remove("dpref_show_editor");
                    this._renderContent();
                }
            },
            () => [this.props.record.isDirty, this.props.value]
        );
    }

    _renderContent() {
        const el = this.containerRef.el;
        if (!el) return;
        el.innerHTML = this.props.value || "";
        if (this._clickHandler) {
            el.removeEventListener("click", this._clickHandler);
        }
        this._clickHandler = (event) => {
            const link = event.target.closest(".oe_direct_line");
            if (link) {
                event.preventDefault();
                this._onClickDirectLink({target: link});
            } else {
                this._switchToEditMode();
            }
        };
        el.addEventListener("click", this._clickHandler);
    }

    _switchToEditMode() {
        const formEl = this.containerRef.el?.closest(".o_form_view");
        if (!formEl) return;
        formEl.classList.add("dpref_show_editor");
        setTimeout(() => {
            const editor = formEl.querySelector(
                ".dpref-content-editor .odoo-editor-editable"
            );
            if (editor) {
                editor.focus();
            }
        }, 50);
    }

    _onClickDirectLink(event) {
        const {oeModel: model, oeId} = event.target.dataset;
        const id = parseInt(oeId, 10);
        this.orm
            .call(model, "get_formview_action", [[id]], {})
            .then((action) => this.action.doAction(action));
    }
}

registry.category("fields").add("document_page_reference", {
    ...htmlField,
    component: DocumentPageReferenceField,
});
