// The read view renders the markdown a turn was written in. Two properties matter
// beyond "does it look right": a code block must not reflow (a wrapped shell
// command is a misread shell command), and nothing in a transcript may reach
// innerHTML unescaped — the text is whatever a tool printed, not what the operator
// typed.

import {
  readApp, extractFunction, extractRegion, evaluate, escapeHtml,
  suite, check, contains, lacks, done,
} from "./harness.mjs";

const src = readApp();
const parts = [
  extractRegion("const MD_FENCE", "\nfunction renderMarkdown", src),
  extractFunction("renderMarkdown", src),
  extractFunction("mdCode", src),
  extractFunction("mdBlocks", src),
  extractFunction("mdInline", src),
].join("\n");
const { renderMarkdown: md } = evaluate(parts, ["renderMarkdown"], { escapeHtml });

suite("markdown — block rendering");
contains("fenced code carries its language", md("```python\nx = 1\n```"),
  '<div class="rd-code-lang">python</div>');
contains("a multi-line block keeps every line", md("```\none\ntwo\nthree\n```"),
  "one\ntwo\nthree");
contains("inline code", md("use `git add -A` now"), '<code class="rd-ic">git add -A</code>');
contains("heading", md("## Title here"), '<div class="rd-h rd-h2">Title here</div>');
contains("unordered list", md("- one\n- two"),
  '<ul class="rd-list"><li>one</li><li>two</li></ul>');
contains("ordered list", md("1. one\n2. two"),
  '<ol class="rd-list"><li>one</li><li>two</li></ol>');
contains("block quote", md("> quoted"), '<blockquote class="rd-quote">quoted</blockquote>');
contains("horizontal rule", md("---"), '<hr class="rd-hr">');
contains("paragraph", md("hello world"), '<p class="rd-p">hello world</p>');
contains("bold", md("this is **very** bad"), "<strong>very</strong>");
contains("italic", md("this is *very* bad"), "<em>very</em>");
contains("markdown link", md("[docs](https://x.io/a)"), '<a href="https://x.io/a"');
contains("bare url", md("see https://x.io/a now"), '<a href="https://x.io/a"');
check("empty input renders nothing", md("") === "");

suite("markdown — a code block is not prose");
check("two blocks stay two blocks",
  (md("```\na\n```\ntext\n```\nb\n```").match(/rd-codewrap/g) || []).length === 2);
contains("prose between blocks survives", md("```\na\n```\nmiddle\n```\nb\n```"), "middle");
lacks("backticks mid-sentence are not a fence", md("use ``` for fences"), "rd-codewrap");
contains("an unterminated fence still shows its code", md("```js\nlet a = 1"), "let a = 1");
contains("markup inside a block stays literal", md("```\n**not bold**\n```"), "**not bold**");
lacks("emphasis never fires inside inline code", md("`a * b * c`"), "<em>");

suite("markdown — untrusted text");
lacks("script tags are escaped", md("<script>alert(1)</script>"), "<script>");
lacks("html inside a code block is escaped", md("```\n<img onerror=x>\n```"), "<img");
lacks("attribute injection via inline code", md('`" onmouseover="evil()`'), 'onmouseover="evil');
check("javascript: link stays inert text",
  !md("[x](javascript:alert(1))").includes("<a ") &&
  md("[x](javascript:alert(1))").includes("[x](javascript:"));
check("data: link stays inert text", !md("[x](data:text/html,<b>)").includes("<a "));
contains("site-relative links are allowed", md("[x](/console/)"), '<a href="/console/"');

suite("markdown — regressions");
contains("digits are not eaten by the hold sentinel", md("the 5 things and 12 more"),
  "the 5 things and 12 more");
lacks("snake_case is not italicised", md("call read_page_now here"), "<em>");
check("a bare url is linked exactly once",
  (md("https://x.io/a").match(/<a /g) || []).length === 1);
check("a wrapped list item stays in its bullet",
  md("- one\n  continued\n- two").includes("one<br>continued"));

done();
