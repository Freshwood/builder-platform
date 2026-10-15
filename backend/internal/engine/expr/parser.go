package expr

// A recursive descent parser for the expression grammar of CPython 3.13 (mode="eval"). It
// accepts the same texts as ast.parse and builds only as much of the tree as the evaluator
// needs: constructs the evaluator rejects are kept as opaque nodes of the right kind.

type nodeKind uint8

const (
	kNum        nodeKind = iota // int, float or bool constant
	kStr                        // str constant
	kConstOther                 // bytes, complex, None, Ellipsis
	kName
	kUnary   // op: "-", "+", "not", "~"
	kBinary  // op: "+", "-", "*", "/", "//", "%", "**", "@", "<<", ">>", "&", "|", "^"
	kBool    // op: "and", "or"
	kCompare // ops: "<", "<=", ">", ">=", "==", "!=", "in", "not in", "is", "is not"
	kIfExp   // kids: test, body, orelse
	kCall    // kids: func, args...
	kAttribute
	kSubscript
	kList
	kTuple
	kDict
	kStarred
	kNamedExpr
	kOther // set, lambda, comprehensions, await, yield, f-strings
)

type node struct {
	kind     nodeKind
	op       string
	ops      []string
	num      float64
	overflow bool
	str      string
	kids     []*node
	keywords bool // call with keyword or ** arguments
	parens   bool // parenthesised (group)
}

type parser struct {
	toks []token
	pos  int
}

// parseSource parses a preprocessed expression; ok is false on any syntax error.
func parseSource(src []rune) (n *node, ok bool) {
	defer func() {
		if r := recover(); r != nil {
			if _, isSyntax := r.(syntaxError); !isSyntax {
				panic(r)
			}
			n, ok = nil, false
		}
	}()
	p := &parser{toks: tokenize(src)}
	n = p.expressions()
	for p.peek().kind == tkNewline {
		p.pos++
	}
	if p.peek().kind != tkEnd {
		fail()
	}
	return n, true
}

// parseFStringExpr validates the expression part of an f-string replacement field.
func parseFStringExpr(toks []token) {
	p := &parser{toks: toks}
	if p.isKw("yield") {
		p.yieldExpr()
	} else {
		p.starExpressions()
	}
	if p.peek().kind != tkEnd {
		fail()
	}
}

func (p *parser) peek() token { return p.toks[p.pos] }

func (p *parser) peekAt(k int) token {
	if p.pos+k >= len(p.toks) {
		return p.toks[len(p.toks)-1]
	}
	return p.toks[p.pos+k]
}

func (p *parser) next() token {
	t := p.toks[p.pos]
	if t.kind != tkEnd {
		p.pos++
	}
	return t
}

func (p *parser) isOp(s string) bool {
	t := p.peek()
	return t.kind == tkOp && t.text == s
}

func (p *parser) isKw(s string) bool {
	t := p.peek()
	return t.kind == tkName && t.text == s
}

func (p *parser) accept(s string) bool {
	if p.isOp(s) || p.isKw(s) {
		p.pos++
		return true
	}
	return false
}

func (p *parser) expect(s string) {
	if !p.accept(s) {
		fail()
	}
}

// isPlainName reports whether the next token is a name that is not a hard keyword.
func (p *parser) isPlainName(k int) bool {
	t := p.peekAt(k)
	return t.kind == tkName && !keywords[t.text]
}

func (p *parser) isCompFor() bool { return p.isKw("for") || p.isKw("async") }

// expressions: expression (',' expression)* [','] at the top level.
func (p *parser) expressions() *node {
	first := p.expression()
	if !p.isOp(",") {
		return first
	}
	elts := []*node{first}
	for p.accept(",") {
		if t := p.peek(); t.kind == tkNewline || t.kind == tkEnd {
			break
		}
		elts = append(elts, p.expression())
	}
	return &node{kind: kTuple, kids: elts}
}

// starExpressions: star_expression (',' star_expression)* [','] (yield values, f-strings).
func (p *parser) starExpressions() *node {
	first := p.starExpression()
	if !p.isOp(",") {
		return first
	}
	elts := []*node{first}
	for p.accept(",") {
		if p.atCloser() {
			break
		}
		elts = append(elts, p.starExpression())
	}
	return &node{kind: kTuple, kids: elts}
}

func (p *parser) atCloser() bool {
	t := p.peek()
	return t.kind == tkEnd || t.kind == tkNewline || (t.kind == tkOp && (t.text == ")" || t.text == "]" || t.text == "}"))
}

func (p *parser) starExpression() *node {
	if p.accept("*") {
		return &node{kind: kStarred, kids: []*node{p.bitwiseOr()}}
	}
	return p.expression()
}

// starNamedExpression: '*' bitwise_or | named_expression.
func (p *parser) starNamedExpression() *node {
	if p.accept("*") {
		return &node{kind: kStarred, kids: []*node{p.bitwiseOr()}}
	}
	return p.namedExpression()
}

// namedExpression: NAME ':=' expression | expression.
func (p *parser) namedExpression() *node {
	if p.isPlainName(0) && p.peekAt(1).kind == tkOp && p.peekAt(1).text == ":=" {
		p.pos += 2
		return &node{kind: kNamedExpr, kids: []*node{p.expression()}}
	}
	return p.expression()
}

func (p *parser) expression() *node {
	if p.isKw("lambda") {
		return p.lambdef()
	}
	body := p.disjunction()
	if p.accept("if") {
		test := p.disjunction()
		p.expect("else")
		orelse := p.expression()
		return &node{kind: kIfExp, kids: []*node{test, body, orelse}}
	}
	return body
}

func (p *parser) boolChain(op string, sub func() *node) *node {
	first := sub()
	if !p.isKw(op) {
		return first
	}
	values := []*node{first}
	for p.accept(op) {
		values = append(values, sub())
	}
	return &node{kind: kBool, op: op, kids: values}
}

func (p *parser) disjunction() *node { return p.boolChain("or", p.conjunction) }

func (p *parser) conjunction() *node { return p.boolChain("and", p.inversion) }

func (p *parser) inversion() *node {
	if p.accept("not") {
		return &node{kind: kUnary, op: "not", kids: []*node{p.inversion()}}
	}
	return p.comparison()
}

func (p *parser) compareOp() string {
	t := p.peek()
	if t.kind == tkOp {
		switch t.text {
		case "==", "!=", "<", "<=", ">", ">=":
			p.pos++
			return t.text
		}
		return ""
	}
	if t.kind != tkName {
		return ""
	}
	switch t.text {
	case "in":
		p.pos++
		return "in"
	case "not":
		if n := p.peekAt(1); n.kind == tkName && n.text == "in" {
			p.pos += 2
			return "not in"
		}
	case "is":
		p.pos++
		if p.accept("not") {
			return "is not"
		}
		return "is"
	}
	return ""
}

func (p *parser) comparison() *node {
	left := p.bitwiseOr()
	var ops []string
	kids := []*node{left}
	for {
		op := p.compareOp()
		if op == "" {
			break
		}
		ops = append(ops, op)
		kids = append(kids, p.bitwiseOr())
	}
	if ops == nil {
		return left
	}
	return &node{kind: kCompare, ops: ops, kids: kids}
}

func (p *parser) binaryLevel(ops []string, sub func() *node) *node {
	left := sub()
	for {
		t := p.peek()
		matched := ""
		if t.kind == tkOp {
			for _, o := range ops {
				if t.text == o {
					matched = o
					break
				}
			}
		}
		if matched == "" {
			return left
		}
		p.pos++
		left = &node{kind: kBinary, op: matched, kids: []*node{left, sub()}}
	}
}

func (p *parser) bitwiseOr() *node  { return p.binaryLevel([]string{"|"}, p.bitwiseXor) }
func (p *parser) bitwiseXor() *node { return p.binaryLevel([]string{"^"}, p.bitwiseAnd) }
func (p *parser) bitwiseAnd() *node { return p.binaryLevel([]string{"&"}, p.shiftExpr) }
func (p *parser) shiftExpr() *node  { return p.binaryLevel([]string{"<<", ">>"}, p.sum) }
func (p *parser) sum() *node        { return p.binaryLevel([]string{"+", "-"}, p.term) }
func (p *parser) term() *node {
	return p.binaryLevel([]string{"*", "/", "//", "%", "@"}, p.factor)
}

func (p *parser) factor() *node {
	for _, op := range []string{"+", "-", "~"} {
		if p.accept(op) {
			return &node{kind: kUnary, op: op, kids: []*node{p.factor()}}
		}
	}
	return p.power()
}

func (p *parser) power() *node {
	base := p.awaitPrimary()
	if p.accept("**") {
		return &node{kind: kBinary, op: "**", kids: []*node{base, p.factor()}}
	}
	return base
}

func (p *parser) awaitPrimary() *node {
	if p.accept("await") {
		p.primary()
		return &node{kind: kOther}
	}
	return p.primary()
}

func (p *parser) primary() *node {
	n := p.atom()
	for {
		switch {
		case p.accept("."):
			if !p.isPlainName(0) {
				fail()
			}
			p.pos++
			n = &node{kind: kAttribute, kids: []*node{n}}
		case p.accept("("):
			n = p.call(n)
		case p.accept("["):
			p.slices()
			n = &node{kind: kSubscript, kids: []*node{n}}
		default:
			return n
		}
	}
}

func (p *parser) atom() *node {
	t := p.peek()
	switch t.kind {
	case tkName:
		switch t.text {
		case "True":
			p.pos++
			return &node{kind: kNum, num: 1}
		case "False":
			p.pos++
			return &node{kind: kNum, num: 0}
		case "None":
			p.pos++
			return &node{kind: kConstOther}
		}
		if keywords[t.text] {
			fail()
		}
		p.pos++
		return &node{kind: kName, str: t.text}
	case tkNumber:
		p.pos++
		if t.complex {
			return &node{kind: kConstOther}
		}
		return &node{kind: kNum, num: t.num, overflow: t.overflow}
	case tkString:
		return p.strings()
	case tkOp:
		switch t.text {
		case "...":
			p.pos++
			return &node{kind: kConstOther}
		case "(":
			p.pos++
			return p.paren()
		case "[":
			p.pos++
			return p.list()
		case "{":
			p.pos++
			return p.braces()
		}
	}
	fail()
	return nil
}

// strings joins implicitly concatenated literals.
func (p *parser) strings() *node {
	var value []byte
	anyBytes, anyText, anyF := false, false, false
	for p.peek().kind == tkString {
		t := p.next()
		if t.bytes {
			anyBytes = true
		} else {
			anyText = true
		}
		if t.fstr {
			anyF = true
		}
		value = append(value, t.value...)
	}
	switch {
	case anyBytes && anyText:
		fail()
	case anyBytes:
		return &node{kind: kConstOther}
	case anyF:
		return &node{kind: kOther}
	}
	return &node{kind: kStr, str: string(value)}
}

func (p *parser) paren() *node {
	if p.accept(")") {
		return &node{kind: kTuple}
	}
	if p.isKw("yield") {
		p.yieldExpr()
		p.expect(")")
		return &node{kind: kOther, parens: true}
	}
	first := p.starNamedExpression()
	if p.isCompFor() {
		if first.kind == kStarred {
			fail()
		}
		p.forIfClauses()
		p.expect(")")
		return &node{kind: kOther}
	}
	if p.isOp(",") {
		elts := []*node{first}
		for p.accept(",") {
			if p.isOp(")") {
				break
			}
			elts = append(elts, p.starNamedExpression())
		}
		p.expect(")")
		return &node{kind: kTuple, kids: elts}
	}
	p.expect(")")
	if first.kind == kStarred {
		fail()
	}
	cp := *first
	cp.parens = true
	return &cp
}

func (p *parser) list() *node {
	if p.accept("]") {
		return &node{kind: kList}
	}
	first := p.starNamedExpression()
	if p.isCompFor() {
		if first.kind == kStarred {
			fail()
		}
		p.forIfClauses()
		p.expect("]")
		return &node{kind: kOther}
	}
	elts := []*node{first}
	for p.accept(",") {
		if p.isOp("]") {
			break
		}
		elts = append(elts, p.starNamedExpression())
	}
	p.expect("]")
	return &node{kind: kList, kids: elts}
}

func (p *parser) braces() *node {
	if p.accept("}") {
		return &node{kind: kDict}
	}
	dict := false
	if p.accept("**") {
		p.bitwiseOr()
		dict = true
	} else {
		first := p.starNamedExpression()
		switch {
		case first.kind != kStarred && p.isOp(":"):
			if first.kind == kNamedExpr && !first.parens {
				fail()
			}
			p.pos++
			p.expression()
			if p.isCompFor() {
				p.forIfClauses()
				p.expect("}")
				return &node{kind: kOther}
			}
			dict = true
		case first.kind != kStarred && p.isCompFor():
			p.forIfClauses()
			p.expect("}")
			return &node{kind: kOther}
		}
	}
	for p.accept(",") {
		if p.isOp("}") {
			break
		}
		if dict {
			if p.accept("**") {
				p.bitwiseOr()
				continue
			}
			p.expression()
			p.expect(":")
			p.expression()
		} else {
			p.starNamedExpression()
		}
	}
	p.expect("}")
	if dict {
		return &node{kind: kDict}
	}
	return &node{kind: kOther}
}

func (p *parser) forIfClauses() {
	for p.isCompFor() {
		p.accept("async")
		p.expect("for")
		p.starTargets()
		p.expect("in")
		p.disjunction()
		for p.accept("if") {
			p.disjunction()
		}
	}
}

// starTargets parses the targets of a comprehension 'for' up to 'in'.
func (p *parser) starTargets() {
	for {
		var t *node
		if p.accept("*") {
			if p.isOp("*") {
				fail()
			}
			t = &node{kind: kStarred, kids: []*node{p.bitwiseOr()}}
		} else {
			t = p.bitwiseOr()
		}
		if !validTarget(t, true) {
			fail()
		}
		if !p.accept(",") || p.isKw("in") {
			return
		}
	}
}

func validTarget(n *node, starOK bool) bool {
	switch n.kind {
	case kName, kAttribute, kSubscript:
		return true
	case kStarred:
		return starOK && n.kids[0].kind != kStarred && validTarget(n.kids[0], false)
	case kTuple, kList:
		for _, k := range n.kids {
			if !validTarget(k, true) {
				return false
			}
		}
		return true
	}
	return false
}

func (p *parser) yieldExpr() {
	p.expect("yield")
	if p.accept("from") {
		p.expression()
		return
	}
	if !p.atCloser() {
		p.starExpressions()
	}
}

func (p *parser) lambdef() *node {
	p.expect("lambda")
	const (
		positional = iota
		withDefaults
		keywordOnly
		kwargs
	)
	state := positional
	slash, anyPositional, bareStar := false, false, false
	for !p.isOp(":") {
		switch {
		case state == kwargs:
			fail()
		case p.accept("/"):
			if slash || state >= keywordOnly || !anyPositional {
				fail()
			}
			slash = true
		case p.accept("*"):
			if state >= keywordOnly {
				fail()
			}
			if p.isPlainName(0) {
				p.pos++
			} else {
				bareStar = true
			}
			state = keywordOnly
		case p.accept("**"):
			if bareStar || !p.isPlainName(0) {
				fail()
			}
			p.pos++
			state = kwargs
		default:
			if !p.isPlainName(0) {
				fail()
			}
			p.pos++
			if p.accept("=") {
				p.expression()
				if state == positional {
					state = withDefaults
				}
			} else if state == withDefaults {
				fail()
			}
			if state < keywordOnly {
				anyPositional = true
			} else {
				bareStar = false
			}
		}
		if !p.accept(",") {
			break
		}
	}
	if bareStar {
		fail()
	}
	p.expect(":")
	p.expression()
	return &node{kind: kOther}
}

// call parses arguments after '(' and returns the Call node.
func (p *parser) call(fn *node) *node {
	n := &node{kind: kCall, kids: []*node{fn}}
	const (
		positional = iota
		named
		doubleStarred
	)
	phase := positional
	first := true
	for !p.isOp(")") {
		switch {
		case p.accept("*"):
			if phase == doubleStarred {
				fail()
			}
			n.kids = append(n.kids, &node{kind: kStarred, kids: []*node{p.expression()}})
		case p.accept("**"):
			p.expression()
			phase = doubleStarred
			n.keywords = true
		case p.isPlainName(0) && p.peekAt(1).kind == tkOp && p.peekAt(1).text == "=":
			p.pos += 2
			p.expression()
			phase = max(phase, named)
			n.keywords = true
		default:
			if phase != positional {
				fail()
			}
			arg := p.namedExpression()
			if p.isOp("=") {
				fail()
			}
			if first && p.isCompFor() {
				p.forIfClauses()
				p.expect(")")
				n.kids = append(n.kids, &node{kind: kOther})
				return n
			}
			n.kids = append(n.kids, arg)
		}
		first = false
		if !p.accept(",") {
			break
		}
	}
	p.expect(")")
	return n
}

// slices parses a subscript after '[' including the closing ']'.
func (p *parser) slices() {
	for {
		if p.accept("*") {
			p.expression()
		} else {
			p.slice()
		}
		if !p.accept(",") || p.isOp("]") {
			break
		}
	}
	p.expect("]")
}

func (p *parser) slice() {
	if !p.isOp(":") {
		lower := p.namedExpression()
		if !p.isOp(":") {
			return
		}
		if lower.kind == kNamedExpr && !lower.parens {
			fail()
		}
	}
	p.expect(":")
	if !p.isOp(":") && !p.isOp("]") && !p.isOp(",") {
		p.expression()
	}
	if p.accept(":") {
		if !p.isOp("]") && !p.isOp(",") {
			p.expression()
		}
	}
}
