"""Small literal HTML source tree, not an Astro renderer or browser DOM."""
from dataclasses import dataclass, field
from html.parser import HTMLParser

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

@dataclass
class Node:
    tag: str
    attrs: dict
    line: int
    parent: object = None
    children: list = field(default_factory=list)

    def text(self):
        return ' '.join(''.join(c.text() if isinstance(c, Node) else c for c in self.children).split())

    def signature(self):
        return (self.tag, sorted(self.attrs.items()), [c.signature() if isinstance(c, Node) else c for c in self.children])

class SourceTree(HTMLParser):
    def __init__(self, content):
        super().__init__(convert_charrefs=True)
        self.root = Node('root', {}, 0)
        self.stack = [self.root]
        self.nodes = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.getpos()[0], self.stack[-1])
        self.nodes.append(node)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)

    @staticmethod
    def matches(node, locator):
        return node.tag == locator['tag'].lower() and all(node.attrs.get(k) == v for k, v in locator.get('attributes', {}).items())

    def select(self, locator):
        selected = []
        for node in self.nodes:
            if not self.matches(node, locator):
                continue
            within = locator.get('within')
            parent = node.parent
            while within and parent and not self.matches(parent, within):
                parent = parent.parent
            if not within or parent:
                selected.append(node)
        return selected
