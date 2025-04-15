from bs4 import BeautifulSoup
import bleach
from bleach.css_sanitizer import CSSSanitizer

ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
	"pf-avatar", "pf-name", "pf-bio", "pf-feed", "pf-status", "pf-banner",
	"style", "div", "span", "section", "p", "h1", "h2", "h3", "h4", "h5", "h6", "br", "hr",
	"a", "img", "video", "source", "blockquote", "pre", "code", "ul", "ol", "li",
	"table", "thead", "tbody", "tr", "th", "td", "mark", "small", "sub", "sup", "del", "ins"
]

ALLOWED_ATTRIBUTES = {
	"*": ["style", "class", "id"],
	"a": ["href", "title", "target"],
	"img": ["src", "alt", "title"],
	"video": ["src", "poster", "width", "height", "controls"],
	"source": ["src", "type"]
}

ALLOWED_STYLES = [
	"color", "background", "background-color", "font-family", "padding", "margin",
	"display", "flex", "grid", "text-align", "justify-content", "align-items",
	"opacity", "font-size", "border", "border-width", "border-color", "border-style", "border-radius",
	"box-shadow", "width", "height", "max-width", "min-width", "max-height", "min-height",
	"line-height", "letter-spacing"
]

css_sanitizer = CSSSanitizer(allowed_css_properties=ALLOWED_STYLES)

def sanitize_html(user_html):
	return bleach.clean(
		user_html,
		tags=ALLOWED_TAGS,
		attributes=ALLOWED_ATTRIBUTES,
		css_sanitizer=css_sanitizer,
		protocols=bleach.sanitizer.ALLOWED_PROTOCOLS,
		strip=False,  # Don't strip disallowed tags—this allows <style> contents to be preserved
		strip_comments=True
	)

def format_html(html):
	soup = BeautifulSoup(html, "html.parser")

	# Extract and move <style> tags to end
	style_tags = soup.find_all("style")
	for style in style_tags:
		style.extract()

	if style_tags:
		body = soup.new_tag("div")
		for tag in soup.contents:
			body.append(tag)
		for style in style_tags:
			body.append(style)
		soup = body

	# Prettify with tab indentation
	pretty = soup.prettify(formatter="html")
	pretty_with_tabs = pretty.replace("    ", "\t")
	return pretty_with_tabs