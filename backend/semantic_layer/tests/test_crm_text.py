"""ZEKI-23: CRM zengin metin alanları ekranda düz metin olarak gösterilir (ortak kural `crm_text`)."""
from semantic_bridge import crm_text as T

WORD = (
    '<!--[if gte mso 9]><xml><o:OfficeDocumentSettings></o:OfficeDocumentSettings></xml><![endif]-->'
    '<style>p.MsoNormal {margin:0}</style>'
    '<p class="MsoNormal"><span style="font-size: 12.0pt; font-family: \'Times New Roman\',serif;">1948&rsquo;de Isparta,\n'
    '&Scedil;arkikaraa&gbreve;a&ccedil;&rsquo;ta do&gbreve;du.<o:p></o:p></span></p>\n'
    '<p class="MsoNormal"><span>&Uuml;niversiteyi bitirdi.</span></p>'
)


def test_word_html_to_paragraphs():
    assert T.rich_text(WORD) == "1948’de Isparta, Şarkikaraağaç’ta doğdu.\nÜniversiteyi bitirdi."


def test_no_markup_left():
    out = T.rich_text(WORD)
    assert "<" not in out and "&" not in out and "mso" not in out.lower() and "margin" not in out


def test_script_dropped_with_content():
    assert T.rich_text('<p>Metin</p><script>alert(1)</script><img src=x onerror=alert(1)>') == "Metin"


def test_double_escaped():
    assert T.rich_text("&lt;p&gt;Birinci&lt;/p&gt;&lt;p&gt;İkinci&lt;/p&gt;") == "Birinci\nİkinci"


def test_plain_text_untouched():
    assert T.rich_text("3 < 5 > 2 ve A & B") == "3 < 5 > 2 ve A & B"
    assert T.rich_text("Birinci satır\nİkinci satır") == "Birinci satır\nİkinci satır"


def test_breaks_and_lists():
    assert T.rich_text("a<br>b<ul><li>x</li><li>y</li></ul>") == "a\nb\n• x\n• y"


def test_keep_blank_and_line():
    assert T.rich_text("a\n\n\n\nb", keep_blank=True) == "a\n\nb"
    assert T.rich_line("<p>a</p><p>b&nbsp;c</p>") == "a b c"


def test_empty():
    assert T.rich_text(None) is None
    assert T.rich_text("<p>&nbsp;</p>") is None
