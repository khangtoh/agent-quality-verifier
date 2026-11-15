package aqv

// The consistency guardrail (C1–C7, A8): the requirements, the contracts and the design say the
// same thing, and stay in step. Every other check compares the code with one document. When two
// documents disagree, an agent builds to one of them, writes tests that agree with its own code,
// and every check passes on a build that is wrong as a whole. These checks look for the
// disagreement itself, before any code exists, and for documents that moved after the build.
//
// On only when .aqv.yml has a `consistency:` section, so a project without one gets the same
// report as before. There is no Python counterpart.
//
//	consistency:
//	  design: ["PLAN.md", "GOAL.md"]     # documents the spec was written from (C4, C6)
//
// Nothing here reads meaning. C1 and C2 read two conventions in a requirement's wording: a status
// code named after "with", "returns" or "status" is an HTTP status, and a word in double quotes is
// a literal value. Two sentences that contradict each other in plain words are not found.

import (
	"fmt"
	"regexp"
	"sort"
	"strings"
)

var ConsistencyCheckIDs = []string{"C1", "C2", "C3", "C4", "C5", "C6", "C7"}

// OutcomeCheck is the one consistency check that reads test evidence, so it sits with the API checks.
const OutcomeCheck = "A8"

func init() {
	for k, v := range map[string]string{
		"C1": "Status codes a requirement names are in the API contract",
		"C2": "Values a requirement quotes are allowed by the contracts",
		"C3": "The API and data contracts agree on shared fields",
		"C4": "The design names only what the contracts have",
		"C5": "Results reset when the requirement's contract changes",
		"C6": "The spec followed the last design change",
		"C7": "The requirement relies on nothing the documents disagree about",
		"A8": "The tagged tests saw every status the requirement names",
	} {
		Checks[k] = v
	}
	for _, c := range []string{"C1", "C2", "C3", "C7"} {
		statusByCheck[c] = "Conflict"
	}
	statusByCheck["C5"] = "Drift"
	statusByCheck["A8"] = "Weak"
	notes["Conflict"] = "The spec, the contracts or the design disagree about it. A person must settle it first."
	// A conflict outranks everything: nothing built on a requirement that contradicts its contract can be trusted.
	statusOrder = append([]string{"Conflict"}, statusOrder...)
}

func (e *Engine) consistencyOn() bool {
	return e.Cfg.Has("consistency") && e.Cfg.Get("consistency") != nil
}

func (e *Engine) designDocs() []string {
	return matching(filesAt(e.Repo, e.Head), strList(e.Cfg.Map("consistency").Get("design")))
}

// ------------------------------------------------------------------ reading a requirement's wording

var (
	// A status code is a known HTTP status that follows a word people use to introduce one
	// ("rejected with 409"), or that continues a list of them ("409 or 422").
	statusInText = regexp.MustCompile(`(?i)\b(?:with|returns?|returning|responds?|status|code|http|gets?)\s+(?:(?:a|an|the|with|status|code|http)\s+)*([1-5][0-9][0-9])\b`)
	statusChain  = regexp.MustCompile(`(?i)^(?:\s*,\s*(?:or\s+|and\s+)?|\s+(?:or|and)\s+)([1-5][0-9][0-9])\b`)
	// A number followed by what it counts is a quantity, not a status: "returns 200 items".
	quantityUnit = regexp.MustCompile(`(?i)^\s*(?:%|ms\b|s\b|seconds?\b|minutes?\b|hours?\b|days?\b|bytes?\b|kb\b|mb\b|items?\b|rows?\b|lines?\b|characters?\b|chars?\b|cents?\b|orders?\b|records?\b|entries\b|results?\b|requests?\b|times\b|per\b)`)
	// In a design document a status is also introduced by what follows it: "409 for a request that conflicts".
	statusBefore = regexp.MustCompile("(?i)(?:^|[\\s(`])([1-5][0-9][0-9])`?\\s+(?:for|when|if|means)\\b")
	quotedValue  = regexp.MustCompile(`["“]([^"“”]{1,40})["”]`)
	opInText     = regexp.MustCompile("\\b(GET|PUT|POST|DELETE|PATCH)\\s+(/[^\\s`,;)]*)")
	idInText     = regexp.MustCompile(`\bAC-[a-z0-9]+(?:-[a-z0-9]+)*-\d{3}\b`)
	pathInTicks  = regexp.MustCompile("`([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+\\.[a-z]{1,5})`")
)

var httpStatuses = map[string]bool{"200": true, "201": true, "202": true, "204": true, "301": true, "302": true,
	"303": true, "304": true, "307": true, "308": true, "400": true, "401": true, "403": true, "404": true,
	"405": true, "406": true, "409": true, "410": true, "412": true, "413": true, "415": true, "422": true,
	"423": true, "428": true, "429": true, "500": true, "501": true, "502": true, "503": true, "504": true}

// statusCodes lists the HTTP status codes a piece of wording names, in order of appearance.
func statusCodes(text string, design bool) []string {
	var out []string
	seen := map[string]bool{}
	add := func(code string, end int) bool {
		if !httpStatuses[code] || quantityUnit.MatchString(text[end:]) {
			return false
		}
		if !seen[code] {
			seen[code] = true
			out = append(out, code)
		}
		return true
	}
	for _, m := range statusInText.FindAllStringSubmatchIndex(text, -1) {
		end := m[3]
		if !add(text[m[2]:m[3]], end) {
			continue
		}
		for {
			c := statusChain.FindStringSubmatchIndex(text[end:])
			if c == nil || !add(text[end+c[2]:end+c[3]], end+c[3]) {
				break
			}
			end += c[3]
		}
	}
	if design {
		for _, m := range statusBefore.FindAllStringSubmatchIndex(text, -1) {
			add(text[m[2]:m[3]], m[3])
		}
	}
	return out
}

// quotedValues lists the words a requirement puts in double quotes.
func quotedValues(text string) []string {
	var out []string
	for _, m := range quotedValue.FindAllStringSubmatch(text, -1) {
		if v := strip(m[1]); v != "" && !contains(out, v) {
			out = append(out, v)
		}
	}
	return out
}

// ------------------------------------------------------------------ reading the contracts

// opNode is one operation as the contract wrote it, with every $ref followed.
func (e *Engine) opNode(op *Operation, doc any) *OMap {
	d, _ := doc.(*OMap)
	item := d.Map("paths").Map(op.Path)
	node, _ := item.Get(strings.ToLower(op.Method)).(*OMap)
	if node == nil {
		return NewOMap()
	}
	out, _ := safeDeref(node, doc).(*OMap)
	if out == nil {
		return NewOMap()
	}
	// Parameters declared on the path apply to every operation under it.
	if shared := asList(safeDeref(item.Get("parameters"), doc)); len(shared) > 0 {
		out.Set("parameters", append(shared, asList(out.Get("parameters"))...))
	}
	return out
}

func safeDeref(node, doc any) (out any) {
	defer func() {
		if recover() != nil {
			out = node // a dangling $ref is A3's problem
		}
	}()
	return deref(node, doc, 0)
}

// fieldFacts is what a contract says about the fields it names: each field's types and allowed values.
type fieldFacts struct {
	types map[string][]string // field name -> JSON types
	enums map[string][]string // field name -> allowed values ("" for an enum with no field name)
	names map[string]bool     // every property and parameter name
}

func newFacts() *fieldFacts {
	return &fieldFacts{map[string][]string{}, map[string][]string{}, map[string]bool{}}
}

func (f *fieldFacts) addEnum(name string, vals []any) {
	for _, v := range vals {
		if s := pyStr(v); !contains(f.enums[name], s) {
			f.enums[name] = append(f.enums[name], s)
		}
	}
}

// walk collects facts from a schema, or from anything that contains schemas.
func (f *fieldFacts) walk(node any, name string) {
	switch x := node.(type) {
	case *OMap:
		if pn := x.Str("name"); pn != "" && x.Has("in") {
			f.names[pn] = true
			f.walk(x.Get("schema"), pn)
			return
		}
		if t := x.Str("type"); t != "" && name != "" && !contains(f.types[name], t) {
			f.types[name] = append(f.types[name], t)
		}
		if vals := asList(x.Get("enum")); len(vals) > 0 {
			f.addEnum(name, vals)
		}
		if x.Has("const") {
			f.addEnum(name, []any{x.Get("const")})
		}
		for _, k := range x.Keys() {
			switch k {
			case "properties":
				props := x.Map(k)
				for _, pn := range props.Keys() {
					f.names[pn] = true
					f.walk(props.Get(pn), pn)
				}
			case "enum", "const", "example", "examples", "default", "description", "summary":
			case "items", "additionalProperties", "not":
				f.walk(x.Get(k), name)
			default:
				f.walk(x.Get(k), "")
			}
		}
	case []any:
		for _, v := range x {
			f.walk(v, name)
		}
	}
}

func (f *fieldFacts) hasEnums() bool { return len(f.enums) > 0 }

func (f *fieldFacts) allows(v string) bool {
	if f.names[v] {
		return true
	}
	for _, vals := range f.enums {
		if contains(vals, v) {
			return true
		}
	}
	return false
}

func (f *fieldFacts) enumText() string {
	var parts []string
	for _, name := range sortedKeys(f.enums) {
		label := name
		if label == "" {
			label = "value"
		}
		parts = append(parts, label+": "+strings.Join(f.enums[name], " | "))
	}
	return strings.Join(parts, "; ")
}

// dataValues reads `values:` lists from a data contract: the allowed values of a column.
func dataValues(doc any, only []string) *fieldFacts {
	f := newFacts()
	root, _ := doc.(*OMap)
	sets := root.Map("datasets")
	for _, name := range sets.Keys() {
		if only != nil && !contains(only, name) {
			continue
		}
		f.names[name] = true
		cols := sets.Map(name).Map("columns")
		for _, cn := range cols.Keys() {
			f.names[cn] = true
			if vals := asList(cols.Map(cn).Get("values")); len(vals) > 0 {
				f.addEnum(cn, vals)
			}
		}
	}
	return f
}

func (f *fieldFacts) merge(g *fieldFacts) {
	for k, v := range g.types {
		for _, t := range v {
			if !contains(f.types[k], t) {
				f.types[k] = append(f.types[k], t)
			}
		}
	}
	for k, v := range g.enums {
		for _, x := range v {
			if !contains(f.enums[k], x) {
				f.enums[k] = append(f.enums[k], x)
			}
		}
	}
	for k := range g.names {
		f.names[k] = true
	}
}

// jsonFamily maps a data contract's column type to the JSON types that can carry it.
var jsonFamily = map[string][]string{"integer": {"integer"}, "real": {"number"}, "numeric": {"number"},
	"text": {"string"}, "blob": {"string"}, "boolean": {"boolean", "integer"}}

// ------------------------------------------------------------------ C1–C7

func (e *Engine) dataDoc() any {
	path := e.dataCfg().Str("contract")
	if path == "" {
		return nil
	}
	text, ok := show(e.Repo, e.Head, path)
	if !ok {
		return nil
	}
	doc, err := loadYAML(text)
	if err != nil {
		return nil
	}
	return doc
}

func (e *Engine) ownOps(r *Requirement) []*Operation {
	var out []*Operation
	for _, mp := range r.APIOps {
		for _, op := range e.ops {
			if op.Key() == opKey(mp) {
				out = append(out, op)
			}
		}
	}
	return out
}

func documented(op *Operation) []string {
	var out []string
	for _, k := range op.Responses.Keys() {
		out = append(out, k)
	}
	return out
}

func documents(op *Operation, code string) bool {
	return op.Responses.Has(code) || op.Responses.Has(head(code, 1)+"XX")
}

func (e *Engine) checkConsistency() {
	if !e.want(ConsistencyCheckIDs...) {
		return
	}
	dataDoc := e.dataDoc()
	global := newFacts()
	global.walk(safeDeref(e.contract, e.contract), "")
	if dataDoc != nil {
		global.merge(dataValues(dataDoc, nil))
		if len(e.datasets) == 0 {
			e.datasets = parseDatasets(dataDoc)
		}
	}
	var disputes []*dispute
	for _, rid := range e.activeIDs {
		r := e.active[rid]
		ops := e.ownOps(r)
		if e.want("C1") {
			e.checkC1(rid, r, ops)
		}
		if e.want("C2") {
			for _, f := range e.checkC2(rid, r, ops, dataDoc, global) {
				disputes = addDispute(disputes, "C2", f, "", rid)
			}
		}
		if e.want("C3") {
			for _, d := range e.checkC3(rid, r, ops) {
				disputes = addDispute(disputes, "C3", d.field, d.dataset, rid)
			}
		}
	}
	if e.want("C7") {
		e.checkC7(disputes, dataDoc, global)
	}
	if e.want("C4") {
		e.checkC4()
	}
	if e.want("C5") {
		e.checkC5()
	}
	if e.want("C6") {
		e.checkC6()
	}
}

// C1: a requirement that says "rejected with 409" needs an operation that documents 409.
func (e *Engine) checkC1(rid string, r *Requirement, ops []*Operation) {
	codes := statusCodes(r.Text, false)
	switch {
	case len(codes) == 0:
		e.add("C1", "requirement", rid, "skip", "Names no status code", nil)
		return
	case len(ops) == 0:
		e.add("C1", "requirement", rid, "fail",
			fmt.Sprintf("Names status %s but is tagged with no operation in the contract", strings.Join(codes, ", ")), nil)
		return
	}
	var missing, problems []string
	for _, code := range codes {
		found := false
		for _, op := range ops {
			found = found || documents(op, code)
		}
		if !found {
			missing = append(missing, code)
		}
	}
	if len(missing) == 0 {
		e.add("C1", "requirement", rid, "pass", "The contract documents "+strings.Join(codes, ", "), nil)
		return
	}
	for _, op := range ops {
		problems = append(problems, fmt.Sprintf("%s documents %s", op.Key(), strings.Join(documented(op), ", ")))
	}
	e.add("C1", "requirement", rid, "fail",
		fmt.Sprintf("The requirement says %s; %s", strings.Join(missing, ", "), strings.Join(problems, "; ")),
		om("requirement_says", missing, "contract_says", problems))
}

// C2: a word a requirement puts in quotes is a literal value, so the contracts must allow it.
// It returns the fields the disagreement is about, for C7.
func (e *Engine) checkC2(rid string, r *Requirement, ops []*Operation, dataDoc any, global *fieldFacts) []string {
	vals := quotedValues(r.Text)
	if len(vals) == 0 {
		e.add("C2", "requirement", rid, "skip", "Quotes no value", nil)
		return nil
	}
	own := newFacts()
	var where []string
	for _, op := range ops {
		own.walk(e.opNode(op, e.contract), "")
		where = append(where, op.Key())
	}
	if dataDoc != nil && len(r.DataSets) > 0 {
		own.merge(dataValues(dataDoc, r.DataSets))
		where = append(where, r.DataSets...)
	}
	// A value may belong to something the requirement's own operations don't show (an order's
	// status, in a requirement about refunds), so fall back to everything the contracts allow.
	scope, label, verb := own, strings.Join(where, ", "), "allows"
	if !own.hasEnums() {
		scope, label, verb = global, "the contracts", "allow"
	}
	if !scope.hasEnums() {
		e.add("C2", "requirement", rid, "not_covered",
			fmt.Sprintf("Quotes %s, and the contracts list no allowed values to compare with", quoteList(vals)), nil)
		return nil
	}
	var bad []string
	for _, v := range vals {
		if !scope.allows(v) && !global.allows(v) {
			bad = append(bad, v)
		}
	}
	if len(bad) == 0 {
		e.add("C2", "requirement", rid, "pass", fmt.Sprintf("%s allowed by %s", quoteList(vals), label), nil)
		return nil
	}
	// The field in dispute is the one the requirement names beside the value ("status"). When it
	// names none, it is every field its own operations and datasets restrict; a value compared
	// against all the contracts points at no field in particular.
	var named, all []string
	for _, name := range sortedKeys(scope.enums) {
		if name == "" {
			continue
		}
		all = append(all, name)
		if wordIn(r.Text, name) {
			named = append(named, name)
		}
	}
	allowed := scope.enumText()
	if len(named) > 0 {
		shown := newFacts()
		for _, name := range named {
			shown.enums[name] = scope.enums[name]
		}
		allowed = shown.enumText()
	}
	e.add("C2", "requirement", rid, "fail",
		fmt.Sprintf("The requirement says %s; %s %s %s", quoteList(bad), label, verb, allowed),
		om("requirement_says", bad, "contract_says", allowed))
	if len(named) > 0 || scope != own {
		return named
	}
	return all
}

// wordIn reports whether text uses a field's name as a word ("unit_price" also as "unit price").
func wordIn(text, name string) bool {
	for _, n := range []string{name, strings.ReplaceAll(name, "_", " ")} {
		if regexp.MustCompile(`(?i)\b` + regexp.QuoteMeta(n) + `\b`).MatchString(text) {
			return true
		}
	}
	return false
}

// dispute is one field the documents disagree about, and the requirements that showed it.
type dispute struct {
	check   string
	field   string
	dataset string   // set when only that dataset's column is in dispute (a type mismatch)
	by      []string // requirements whose C2 or C3 failed on it
}

func addDispute(ds []*dispute, check, field, dataset, rid string) []*dispute {
	for _, d := range ds {
		if d.check == check && d.field == field && d.dataset == dataset {
			if !contains(d.by, rid) {
				d.by = append(d.by, rid)
			}
			return ds
		}
	}
	return append(ds, &dispute{check, field, dataset, []string{rid}})
}

// C7: a disagreement about a field reaches every requirement that carries that field, not only
// the one whose wording showed it. Whichever way a person settles it, what those requirements
// return or store may change, so they can't be proven either until it is settled.
func (e *Engine) checkC7(disputes []*dispute, dataDoc any, global *fieldFacts) {
	shows := map[string]bool{}
	for _, r := range e.Results {
		if r.Scope == "requirement" && r.Verdict == "fail" && (r.Check == "C1" || r.Check == "C2" || r.Check == "C3") {
			shows[r.Subject] = true
		}
	}
	for _, rid := range e.activeIDs {
		r := e.active[rid]
		if shows[rid] {
			e.add("C7", "requirement", rid, "skip", "Shows a disagreement itself", nil)
			continue
		}
		own := newFacts()
		for _, op := range e.ownOps(r) {
			own.walk(e.opNode(op, e.contract), "")
		}
		if dataDoc != nil && len(r.DataSets) > 0 {
			own.merge(dataValues(dataDoc, r.DataSets))
		}
		quoted := quotedValues(r.Text)
		var fields, because, problems []string
		for _, d := range disputes {
			why := ""
			switch {
			case d.dataset != "":
				if contains(r.DataSets, d.dataset) {
					why = fmt.Sprintf("Uses %s, where %s is in dispute", d.dataset, d.field)
				}
			case len(own.enums[d.field]) > 0:
				why = fmt.Sprintf("Carries %s, which is in dispute", d.field)
			default:
				for _, v := range quoted {
					if contains(global.enums[d.field], v) {
						why = fmt.Sprintf(`Quotes "%s", a value of %s, which is in dispute`, v, d.field)
						break
					}
				}
			}
			if why == "" {
				continue
			}
			if !contains(fields, d.field) {
				fields = append(fields, d.field)
			}
			for _, by := range d.by {
				if ref := d.check + " " + by; !contains(because, ref) {
					because = append(because, ref)
				}
			}
			problems = append(problems, fmt.Sprintf("%s (see %s on %s)", why, d.check, strings.Join(d.by, ", ")))
		}
		if len(problems) == 0 {
			e.add("C7", "requirement", rid, "pass", "Relies on nothing the documents disagree about", nil)
			continue
		}
		e.add("C7", "requirement", rid, "fail", shown(problems, 3),
			om("relies_on", fields, "because", because, "problems", problems))
	}
}

func quoteList(vals []string) string {
	out := make([]string, len(vals))
	for i, v := range vals {
		out[i] = `"` + v + `"`
	}
	return strings.Join(out, ", ")
}

// C3: a field with the same name in a requirement's operations and in its datasets is the same
// fact published twice, so its type and allowed values must match.
// It returns what the two contracts disagree about, for C7.
func (e *Engine) checkC3(rid string, r *Requirement, ops []*Operation) []dispute {
	if len(ops) == 0 || len(r.DataSets) == 0 || len(e.datasets) == 0 {
		e.add("C3", "requirement", rid, "skip", "Not both an API and a data requirement", nil)
		return nil
	}
	api := newFacts()
	for _, op := range ops {
		api.walk(e.opNode(op, e.contract), "")
	}
	values := dataValues(e.dataDoc(), r.DataSets)
	byName := datasetsByName(e.datasets)
	var problems []string
	var found []dispute
	shared := 0
	for _, name := range r.DataSets {
		d := byName[name]
		if d == nil {
			continue
		}
		for _, col := range d.Columns {
			types := api.types[col.Name]
			if len(types) == 0 {
				continue
			}
			shared++
			want := jsonFamily[col.Type]
			ok := false
			for _, t := range types {
				ok = ok || contains(want, t)
			}
			if !ok && len(want) > 0 {
				problems = append(problems, fmt.Sprintf("%s is %s in the API contract and %s in %s",
					col.Name, strings.Join(types, " or "), col.Type, name))
				found = append(found, dispute{field: col.Name, dataset: name})
			}
			a, b := api.enums[col.Name], values.enums[col.Name]
			if len(a) > 0 && len(b) > 0 && strings.Join(uniqSorted(a), "|") != strings.Join(uniqSorted(b), "|") {
				problems = append(problems, fmt.Sprintf("%s allows %s in the API contract and %s in %s",
					col.Name, strings.Join(a, " | "), strings.Join(b, " | "), name))
				found = append(found, dispute{field: col.Name})
			}
		}
	}
	switch {
	case len(problems) > 0:
		e.add("C3", "requirement", rid, "fail", shown(problems, 3), om("problems", problems))
	case shared == 0:
		e.add("C3", "requirement", rid, "skip", "Its operations and datasets share no field name", nil)
	default:
		e.add("C3", "requirement", rid, "pass", fmt.Sprintf("%d shared field(s) agree", shared), nil)
	}
	return found
}

// C4: the design documents were the starting point of the spec. An operation, a status code, a
// requirement or a file they name that doesn't exist means the design and the spec have parted.
func (e *Engine) checkC4() {
	docs := e.designDocs()
	if len(docs) == 0 {
		e.add("C4", "project", "design", "not_covered", "No design documents listed (consistency.design)", nil)
		return
	}
	files := map[string]bool{}
	for _, f := range filesAt(e.Repo, e.Head) {
		files[f] = true
	}
	var problems []string
	named := 0
	for _, path := range docs {
		text, _ := show(e.Repo, e.Head, path)
		for _, m := range opInText.FindAllStringSubmatch(text, -1) {
			named++
			if p := strings.TrimRight(m[2], "."); findOp(e.ops, m[1], p) == nil && !hasOpPath(e.ops, m[1], p) {
				problems = append(problems, fmt.Sprintf("%s describes %s %s, which the contract doesn't have", path, m[1], p))
			}
		}
		for _, code := range statusCodes(text, true) {
			named++
			found := false
			for _, op := range e.ops {
				found = found || documents(op, code)
			}
			if !found && len(e.ops) > 0 {
				problems = append(problems, fmt.Sprintf("%s says status %s, which no operation documents", path, code))
			}
		}
		for _, id := range idInText.FindAllString(text, -1) {
			named++
			if _, ok := e.active[id]; !ok {
				problems = append(problems, fmt.Sprintf("%s refers to %s, which is not a live requirement", path, id))
			}
		}
		for _, m := range pathInTicks.FindAllStringSubmatch(text, -1) {
			named++
			if !files[m[1]] {
				problems = append(problems, fmt.Sprintf("%s refers to %s, which doesn't exist", path, m[1]))
			}
		}
	}
	problems = uniqSorted(problems)
	if len(problems) > 0 {
		e.add("C4", "project", "design", "fail", shown(problems, 3), om("problems", problems))
		return
	}
	e.add("C4", "project", "design", "pass",
		fmt.Sprintf("%d reference(s) in %s resolve", named, strings.Join(docs, ", ")), nil)
}

func hasOpPath(ops []*Operation, method, path string) bool {
	for _, op := range ops {
		if op.Method == method && op.Path == path {
			return true
		}
	}
	return false
}

// contractSlice is what the contracts say about one requirement: its operations and its datasets,
// flattened to "path = value" lines so two versions can be compared and the difference named.
func (e *Engine) contractSlice(r *Requirement, api, data any) map[string]string {
	out := map[string]string{}
	for _, mp := range r.APIOps {
		for _, op := range operations(api) {
			if op.Key() == opKey(mp) {
				node := e.opNode(op, api)
				node.Delete("x-requirements")
				flatten(node, op.Key(), out)
			}
		}
	}
	root, _ := data.(*OMap)
	for _, name := range r.DataSets {
		if d, ok := root.Map("datasets").Get(name).(*OMap); ok {
			c, _ := deepCopy(d).(*OMap)
			c.Delete("x-requirements")
			flatten(c, name, out)
		}
	}
	return out
}

// noise is wording in a contract that doesn't change what a build must do.
var noise = map[string]bool{"description": true, "summary": true, "example": true, "examples": true, "tags": true,
	"operationId": true}

func flatten(node any, prefix string, out map[string]string) {
	switch x := node.(type) {
	case *OMap:
		for _, k := range x.Keys() {
			if !noise[k] {
				flatten(x.Get(k), prefix+" › "+k, out)
			}
		}
	case []any:
		scalars := true
		for _, v := range x {
			switch v.(type) {
			case *OMap, []any:
				scalars = false
			}
		}
		if scalars {
			parts := make([]string, len(x))
			for i, v := range x {
				parts[i] = pyStr(v)
			}
			out[prefix] = "[" + strings.Join(parts, ", ") + "]"
			return
		}
		for i, v := range x {
			key := fmt.Sprintf("%d", i)
			if m, ok := v.(*OMap); ok && m.Str("name") != "" {
				key = m.Str("name")
			}
			flatten(v, prefix+" › "+key, out)
		}
	default:
		out[prefix] = pyStr(node)
	}
}

func sliceDiff(old, new map[string]string) []string {
	var out []string
	for _, k := range sortedKeys(new) {
		if o, ok := old[k]; !ok {
			out = append(out, "+ "+k+" = "+new[k])
		} else if o != new[k] {
			out = append(out, k+": "+o+" → "+new[k])
		}
	}
	for _, k := range sortedKeys(old) {
		if _, ok := new[k]; !ok {
			out = append(out, "− "+k+" = "+old[k])
		}
	}
	return out
}

func sliceKey(m map[string]string) string {
	var b strings.Builder
	for _, k := range sortedKeys(m) {
		b.WriteString(k + "=" + m[k] + "\n")
	}
	return b.String()
}

// C5 is T8 for the contracts: a requirement whose operations or datasets changed after its last
// code or test commit was built against a contract that no longer exists.
func (e *Engine) checkC5() {
	var paths []string
	for _, p := range []string{e.Cfg.Str("contract"), e.dataCfg().Str("contract")} {
		if p != "" {
			paths = append(paths, p)
		}
	}
	type version struct {
		sha       string
		api, data any
	}
	var hist []version
	if len(paths) > 0 {
		for _, sha := range fields(git(e.Repo, append([]string{"log", "--reverse", "--format=%H", e.Head, "--"}, paths...)...)) {
			v := version{sha: sha}
			if t, ok := show(e.Repo, sha, e.Cfg.Str("contract")); ok && e.Cfg.Str("contract") != "" {
				v.api, _ = loadYAML(t)
			}
			if t, ok := show(e.Repo, sha, e.dataCfg().Str("contract")); ok && e.dataCfg().Str("contract") != "" {
				v.data, _ = loadYAML(t)
			}
			hist = append(hist, v)
		}
	}
	for _, rid := range e.activeIDs {
		r := e.active[rid]
		impl := e.linkedAny[rid]
		switch {
		case len(r.APIOps) == 0 && len(r.DataSets) == 0:
			e.add("C5", "requirement", rid, "skip", "Has no operation or dataset", nil)
			continue
		case len(impl) == 0:
			e.add("C5", "requirement", rid, "skip", "Not implemented yet", nil)
			continue
		}
		changedAt := ""
		var before, prev map[string]string
		for _, v := range hist {
			cur := e.contractSlice(r, v.api, v.data)
			if prev == nil || sliceKey(cur) != sliceKey(prev) {
				changedAt, before = v.sha, prev
			}
			prev = cur
		}
		if changedAt == "" {
			e.add("C5", "requirement", rid, "skip", "No contract history", nil)
			continue
		}
		fresh := false
		for _, cm := range impl {
			fresh = fresh || isAncestor(e.Repo, changedAt, cm.SHA)
		}
		if fresh {
			e.add("C5", "requirement", rid, "pass",
				fmt.Sprintf("Implemented or re-verified after its contract last changed (%s)", head(changedAt, 7)), nil)
			continue
		}
		diff := sliceDiff(before, prev)
		e.add("C5", "requirement", rid, "fail",
			fmt.Sprintf("Its contract changed in %s after its last code or test commit: %s", head(changedAt, 7), shown(diff, 2)),
			om("changed_in", changedAt, "changes", diff))
	}
}

// C6: the design is upstream of the spec. A design document that changes after code exists, with
// no requirement or contract changing with it or after it, leaves the spec describing the old design.
func (e *Engine) checkC6() {
	docs := e.designDocs()
	if len(docs) == 0 {
		e.add("C6", "project", "design", "not_covered", "No design documents listed (consistency.design)", nil)
		return
	}
	last := strip(git(e.Repo, append([]string{"log", "-1", "--format=%H", e.Head, "--"}, docs...)...))
	if last == "" {
		e.add("C6", "project", "design", "skip", "The design documents have no history", nil)
		return
	}
	built := 0
	for _, rid := range e.activeIDs {
		for _, cm := range e.linkedCode[rid] {
			if cm.SHA != last && isAncestor(e.Repo, cm.SHA, last) {
				built++
				break
			}
		}
	}
	if built == 0 {
		e.add("C6", "project", "design", "pass",
			fmt.Sprintf("The design last changed in %s, before any requirement was built", head(last, 7)), nil)
		return
	}
	specPaths := append(strList(e.Cfg.Get("specs")), e.Cfg.Str("contract"))
	if p := e.dataCfg().Str("contract"); p != "" {
		specPaths = append(specPaths, p)
	}
	var live []string
	for _, p := range specPaths {
		if p != "" {
			live = append(live, p)
		}
	}
	followed := strip(git(e.Repo, append([]string{"log", "--format=%H", last + "^.." + e.Head, "--"}, live...)...))
	if followed != "" {
		e.add("C6", "project", "design", "pass",
			fmt.Sprintf("The spec or a contract changed with or after the last design change (%s)", head(last, 7)), nil)
		return
	}
	humans := strList(e.gitCfg().Get("humans"))
	meta := strings.SplitN(strip(git(e.Repo, "log", "-1", "--format=%ae%x00%(trailers:key=Spec-Impact,valueonly,separator=%x2C)", last)), "\x00", 2)
	if len(meta) == 2 && strings.EqualFold(strip(meta[1]), "none") && (len(humans) == 0 || contains(humans, meta[0])) {
		e.add("C6", "project", "design", "pass",
			fmt.Sprintf("The last design change (%s) is marked Spec-Impact: none by a person", head(last, 7)), nil)
		return
	}
	changed := fields(git(e.Repo, append([]string{"show", "--format=", "--name-only", last, "--"}, docs...)...))
	sort.Strings(changed)
	e.add("C6", "project", "design", "fail",
		fmt.Sprintf("%s changed in %s after %d requirement(s) were built, and no requirement or contract changed with it. "+
			"Carry the change into the spec, or mark the commit Spec-Impact: none", strings.Join(changed, ", "), head(last, 7), built),
		om("changed_in", last, "documents", changed, "built_before", built))
}

// ------------------------------------------------------------------ A8

// checkA8: the agent's tests agree with the agent's code, so passing tests don't show that the
// code does what the requirement says. Where the requirement names a status code, a tagged test
// must have seen that status from one of the requirement's operations.
func (e *Engine) checkA8(apiReqs []string) {
	if !e.want(OutcomeCheck) {
		return
	}
	if !e.captureEnabled() {
		for _, rid := range apiReqs {
			e.add("A8", "requirement", rid, "not_covered", "No test-traffic adapter for this framework", nil)
		}
		return
	}
	if e.suite == nil || e.suite.Broken {
		for _, rid := range apiReqs {
			e.add("A8", "requirement", rid, "skip", "Test suite didn't run", nil)
		}
		return
	}
	calls := e.readCapture()
	for _, rid := range apiReqs {
		r := e.active[rid]
		codes := statusCodes(r.Text, false)
		if len(codes) == 0 {
			e.add("A8", "requirement", rid, "skip", "Names no status code", nil)
			continue
		}
		own := map[string]bool{}
		for _, mp := range r.APIOps {
			own[opKey(mp)] = true
		}
		saw := map[string]bool{}
		tagged := 0
		for _, c := range calls {
			if !c.Has("test") || !mentions(pyStr(c.Get("test")), rid) {
				continue
			}
			tagged++
			op := findOp(e.ops, pyStr(c.Get("method")), strings.SplitN(pyStr(c.Get("path")), "?", 2)[0])
			if op != nil && own[op.Key()] {
				saw[pyStr(c.Get("status"))] = true
			}
		}
		if tagged == 0 {
			e.add("A8", "requirement", rid, "skip", "No tagged test traffic yet", nil)
			continue
		}
		var missing []string
		for _, code := range codes {
			if !saw[code] {
				missing = append(missing, code)
			}
		}
		if len(missing) == 0 {
			e.add("A8", "requirement", rid, "pass", "Tagged tests saw "+strings.Join(codes, ", "), nil)
			continue
		}
		seen := strings.Join(sortedKeys(saw), ", ")
		if seen == "" {
			seen = "no response"
		}
		e.add("A8", "requirement", rid, "fail",
			fmt.Sprintf("The requirement says %s; its tagged tests saw only %s from %s",
				strings.Join(missing, ", "), seen, strings.Join(sortedKeys(own), ", ")),
			om("never_seen", missing, "seen", sortedKeys(saw)))
	}
}
