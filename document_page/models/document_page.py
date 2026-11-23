# Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import re

from lxml import etree, html

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_HISTORY_STEPS_RE = re.compile(r'\sdata-last-history-steps="[^"]*"')
_INTER_TAG_WS_RE = re.compile(r">\s+<")
_WHITESPACE_RE = re.compile(r"\s+")


class DocumentPage(models.Model):
    """This class is use to manage Document."""

    _name = "document.page"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Document Page"
    _order = "name"

    _HTML_WIDGET_DEFAULT_VALUE = "<p><br></p>"

    name = fields.Char("Title", required=True)
    type = fields.Selection(
        [("content", "Content"), ("category", "Category")],
        help="Page type",
        default="content",
    )
    active = fields.Boolean(default=True)
    parent_id = fields.Many2one(
        "document.page", "Category", domain=[("type", "=", "category")]
    )
    child_ids = fields.One2many("document.page", "parent_id", "Children")
    content = fields.Html(
        compute="_compute_content",
        inverse="_inverse_content",
        search="_search_content",
        sanitize=False,
    )

    draft_name = fields.Char(
        string="Name",
        help="Name for the changes made",
        related="history_head.name",
        readonly=False,
    )

    draft_summary = fields.Char(
        string="Summary",
        help="Describe the changes made",
        related="history_head.summary",
        readonly=False,
    )

    template = fields.Html(
        help="Template that will be used as a content template "
        "for all new page of this category.",
    )
    history_head = fields.Many2one(
        "document.page.history",
        "HEAD",
        compute="_compute_history_head",
        store=True,
        auto_join=True,
    )
    history_ids = fields.One2many(
        "document.page.history",
        "page_id",
        "History",
        readonly=True,
    )
    menu_id = fields.Many2one("ir.ui.menu", "Menu", readonly=True)
    content_date = fields.Datetime(
        "Last Contribution Date",
        related="history_head.create_date",
        store=True,
        index=True,
        readonly=True,
    )
    content_uid = fields.Many2one(
        "res.users",
        "Last Contributor",
        related="history_head.create_uid",
        store=True,
        index=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        "Company",
        help="If set, page is accessible only from this company",
        index=True,
        ondelete="cascade",
        default=lambda self: self.env.company,
    )
    backend_url = fields.Char(
        string="Backend URL",
        help="Use it to link resources univocally",
        compute="_compute_backend_url",
    )

    image = fields.Binary(attachment=True)
    color = fields.Integer(string="Color Index")

    @api.depends("menu_id", "parent_id.menu_id")
    def _compute_backend_url(self):
        tmpl = "/web#id={}&model=document.page&view_type=form"
        for rec in self:
            url = tmpl.format(rec.id)
            # retrieve action
            action = None
            parent = rec
            while not action and parent:
                action = parent.menu_id.action
                parent = parent.parent_id
            if action:
                url += f"&action={action.id}"
            rec.backend_url = url

    @api.constrains("parent_id")
    def _check_parent_id(self):
        if self._has_cycle():
            raise ValidationError(self.env._("You cannot create recursive categories."))

    def _get_page_index(self, link=True):
        """Return the index of a document."""
        self.ensure_one()
        index = [
            "<li>" + subpage._get_page_index() + "</li>" for subpage in self.child_ids
        ]
        r = ""
        if link:
            r = f'<a href="{self.backend_url}">{self.name}</a>'
        if index:
            r += "<ul>" + "".join(index) + "</ul>"
        return r

    @api.depends("history_head")
    def _compute_content(self):
        for rec in self:
            if rec.type == "category":
                rec.content = rec._get_page_index(link=False)
            else:
                if rec.history_head:
                    rec.content = rec.history_head.content
                else:
                    # html widget's default, so it doesn't trigger ghost save
                    rec.content = self._HTML_WIDGET_DEFAULT_VALUE

    @api.model
    def _normalize_content(self, content):
        """Return a canonical form of the HTML, used to detect real changes.

        The HTML editor adds ``data-last-history-steps`` in collaborative mode
        and may reformat the markup when a page is only opened, which must not
        produce a new history entry.
        """
        content = _HISTORY_STEPS_RE.sub("", content or "")
        try:
            fragments = html.fragments_fromstring(content)
        except (etree.ParserError, ValueError):
            fragments = [content]
        content = "".join(
            frag if isinstance(frag, str) else html.tostring(frag, encoding="unicode")
            for frag in fragments
        )
        content = _WHITESPACE_RE.sub(" ", _INTER_TAG_WS_RE.sub("><", content)).strip()
        if content in ("", self._HTML_WIDGET_DEFAULT_VALUE):
            return ""
        return content

    def _is_content_changed(self, old_content):
        self.ensure_one()
        return self._normalize_content(self.content) != self._normalize_content(
            old_content
        )

    def _inverse_content(self):
        for rec in self:
            if rec.type == "content" and rec._is_content_changed(
                rec.history_head.content
            ):
                rec._create_history(
                    {
                        "page_id": rec.id,
                        "name": rec.draft_name,
                        "summary": rec.draft_summary,
                        "content": rec.content,
                    }
                )

    def _create_history(self, vals):
        self.ensure_one()
        return self.env["document.page.history"].create(vals)

    def _search_content(self, operator, value):
        return [("history_head.content", operator, value)]

    @api.depends("history_ids")
    def _compute_history_head(self):
        for rec in self:
            if rec.history_ids:
                rec.history_head = rec.history_ids[0]
            else:
                rec.history_head = False

    @api.onchange("parent_id")
    def _onchange_parent_id(self):
        """We Set it the right content to the new parent."""
        if (
            self.content in (False, self._HTML_WIDGET_DEFAULT_VALUE)
            and self.parent_id.type == "category"
        ):
            self.content = self.parent_id.template

    def unlink(self):
        menus = self.mapped("menu_id")
        res = super().unlink()
        menus.unlink()
        return res

    def copy(self, default=None):
        default = dict(
            default or {},
            name=self.env._("%s (copy)") % self.name,
            content=self.content,
            draft_name="1.0",
            draft_summary=self.env._("summary"),
        )
        return super().copy(default=default)
