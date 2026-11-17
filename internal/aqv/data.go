package aqv

// The data guardrail (D1–D7): the database matches its data contract, and derived data comes only
// from the sources it declares. These checks run only when .aqv.yml has a `data:` section, so a
// project without one gets the same report as before. There is no Python counterpart.
//
// The data contract (contracts/data.yaml) lists every dataset:
//
//	datasets:
//	  payments:
//	    kind: source                      # source: written by the service; derived: built from others
//	    x-requirements: [AC-led-005]
//	    primary_key: [id]
//	    columns:
//	      id:           {type: integer, nullable: false}
//	      order_id:     {type: integer, nullable: false}
//	      amount_cents: {type: integer, nullable: false}
//	    foreign_keys:
//	      - {columns: [order_id], references: orders.id}
//	  daily_revenue:
//	    kind: derived
//	    x-requirements: [AC-led-009]
//	    columns:
//	      day:         {type: text,    nullable: false, from: [payments.captured_on]}
//	      gross_cents: {type: integer, nullable: false, from: [payments.amount_cents]}

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

var DataCheckIDs = []string{"D1", "D2", "D3", "D4", "D5", "D6", "D7"}

// ProtectCheck is on only when git.protect is set.
const ProtectCheck = "H10"

func init() {
	for k, v := range map[string]string{
		"D1":  "Every data requirement has a dataset",
		"D2":  "Every dataset references a requirement",
		"D3":  "The data contract is complete and consistent",
		"D4":  "No breaking data change unless the spec changed",
		"D5":  "The database has exactly the declared schema",
		"D6":  "Derived data reads only its declared sources",
		"D7":  "Merged migrations are never edited",
		"H10": "Protected files are changed only by people",
	} {
		Checks[k] = v
	}
	for _, c := range []string{"D1", "D5", "D6"} {
		statusByCheck[c] = "Data"
	}
	notes["Data"] = "The database doesn't honor its data contract for this requirement."
}

var (
	dataTypes   = []string{"integer", "real", "numeric", "text", "blob", "boolean"}
	datasetName = regexp.MustCompile(`^[a-z_][a-z0-9_]*$`)
)

type DataColumn struct {
	Name, Type string
	Nullable   any // bool, or nil when the contract doesn't say
	From       []string
}

type DataFK struct {
	Columns    []string
	References string
}

func (f DataFK) Key() string { return strings.Join(f.Columns, ",") + " -> " + f.References }

type Dataset struct {
	Name, Kind   string
	Requirements []string
	PrimaryKey   []string
	Columns      []*DataColumn
	FKs          []DataFK
	Reads        []string // observed schema only: the columns a view reads
	Error        string   // observed schema only: why the database can't read this dataset
}

func (d *Dataset) column(name string) *DataColumn {
	for _, c := range d.Columns {
		if c.Name == name {
			return c
		}
	}
	return nil
}

// sources is every column the dataset declares it is built from.
func (d *Dataset) sources() []string {
	var out []string
	for _, c := range d.Columns {
		out = append(out, c.From...)
	}
	return uniqSorted(out)
}

// parseDatasets reads the `datasets` mapping of a data contract or of an observed schema.
func parseDatasets(doc any) []*Dataset {
	root, _ := doc.(*OMap)
	sets := root.Map("datasets")
	var out []*Dataset
	for _, name := range sets.Keys() {
		m := sets.Map(name)
		d := &Dataset{Name: name, Kind: m.Str("kind"), Requirements: strList(m.Get("x-requirements")),
			PrimaryKey: strList(m.Get("primary_key")), Reads: uniqSorted(strList(m.Get("reads"))), Error: m.Str("error")}
		cols := m.Map("columns")
		for _, cn := range cols.Keys() {
			cm := cols.Map(cn)
			d.Columns = append(d.Columns, &DataColumn{Name: cn, Type: strings.ToLower(cm.Str("type")),
				Nullable: cm.Get("nullable"), From: strList(cm.Get("from"))})
		}
		for _, f := range maps(m.Get("foreign_keys")) {
			d.FKs = append(d.FKs, DataFK{strList(f.Get("columns")), f.Str("references")})
		}
		out = append(out, d)
	}
	return out
}

func datasetsByName(ds []*Dataset) map[string]*Dataset {
	out := map[string]*Dataset{}
	for _, d := range ds {
		out[d.Name] = d
	}
	return out
}

func (e *Engine) dataCfg() *OMap { return e.Cfg.Map("data") }

// enableExtras turns on the checks that depend on config: D1–D7 with a `data:` section, H10 with
// git.protect. It runs after the config is loaded.
func (e *Engine) enableExtras(o Options) {
	if e.dataCfg().Str("contract") != "" {
		e.extra = append(e.extra, DataCheckIDs...)
	}
	if e.gitCfg().Truthy("protect") {
		e.extra = append(e.extra, ProtectCheck)
	}
	if e.consistencyOn() {
		e.extra = append(e.extra, ConsistencyCheckIDs...)
		e.extra = append(e.extra, OutcomeCheck)
	}
	for _, c := range e.extra {
		if (len(o.Only) == 0 || contains(o.Only, c)) && !o.Light && !contains(o.Skip, c) {
			e.wanted[c] = true
		}
	}
}

func (e *Engine) dataReqs() []string {
	var out []string
	for _, rid := range e.activeIDs {
		if len(e.active[rid].DataSets) > 0 {
			out = append(out, rid)
		}
	}
	return out
}

func shown(xs []string, n int) string {
	if len(xs) > n {
		xs = xs[:n]
	}
	return strings.Join(xs, "; ")
}

func (e *Engine) checkData() {
	if !e.want(DataCheckIDs...) {
		return
	}
	dataReqs := e.dataReqs()
	path := e.dataCfg().Str("contract")
	text, ok := show(e.Repo, e.Head, path)
	if !ok || strip(text) == "" {
		for _, rid := range dataReqs {
			e.add("D1", "requirement", rid, "fail", "No data contract at "+path, nil)
		}
		e.checkD7()
		return
	}
	doc, err := loadYAML(text)
	if err != nil {
		e.add("D3", "project", "data contract", "error", "Can't parse the data contract: "+err.Error(), nil)
		e.checkD7()
		return
	}
	e.datasets = parseDatasets(doc)
	byName := datasetsByName(e.datasets)

	// D1: every data requirement names datasets the contract has, and they name it back.
	for _, rid := range e.activeIDs {
		r := e.active[rid]
		if len(r.DataSets) == 0 {
			e.add("D1", "requirement", rid, "skip", "Not a data requirement", nil)
			continue
		}
		var problems []string
		for _, name := range r.DataSets {
			d := byName[name]
			if d == nil {
				problems = append(problems, name+" is not in the data contract")
			} else if !contains(d.Requirements, rid) {
				problems = append(problems, fmt.Sprintf("%s doesn't list %s in x-requirements", name, rid))
			}
		}
		if len(problems) > 0 {
			e.add("D1", "requirement", rid, "fail", strings.Join(problems, "; "), nil)
		} else {
			e.add("D1", "requirement", rid, "pass", "Data contract covers "+strings.Join(r.DataSets, ", "), nil)
		}
	}
	// D2: every dataset is explained by a live requirement.
	for _, d := range e.datasets {
		var unknown []string
		for _, x := range d.Requirements {
			if _, ok := e.active[x]; !ok {
				unknown = append(unknown, x)
			}
		}
		switch {
		case len(d.Requirements) == 0:
			e.add("D2", "dataset", d.Name, "fail", d.Name+" references no requirement", nil)
		case len(unknown) > 0:
			e.add("D2", "dataset", d.Name, "fail",
				fmt.Sprintf("%s references unknown or retired requirement(s): %s", d.Name, strings.Join(unknown, ", ")), nil)
		default:
			e.add("D2", "dataset", d.Name, "pass", d.Name+" → "+strings.Join(d.Requirements, ", "), nil)
		}
	}
	if e.want("D3") {
		if problems := lintDatasets(e.datasets); len(problems) > 0 {
			e.add("D3", "project", "data contract", "fail",
				fmt.Sprintf("%d problem(s): %s", len(problems), shown(problems, 3)), om("problems", problems))
		} else {
			e.add("D3", "project", "data contract", "pass",
				fmt.Sprintf("%d dataset(s) fully declared, lineage resolves", len(e.datasets)), nil)
		}
	}
	if e.want("D4") {
		e.checkD4(path)
	}
	if e.want("D5", "D6") {
		e.checkD5D6(dataReqs)
	}
	e.checkD7()
}

// lintDatasets is D3: the contract says enough to be checked, and its lineage is consistent.
func lintDatasets(ds []*Dataset) []string {
	byName := datasetsByName(ds)
	var problems []string
	for _, d := range ds {
		if !datasetName.MatchString(d.Name) {
			problems = append(problems, d.Name+": dataset names are lower_snake_case")
		}
		if d.Kind != "source" && d.Kind != "derived" {
			problems = append(problems, d.Name+": kind must be source or derived")
		}
		if len(d.Columns) == 0 {
			problems = append(problems, d.Name+": no columns")
		}
		if d.Kind == "source" && len(d.PrimaryKey) == 0 {
			problems = append(problems, d.Name+": a source dataset needs a primary_key")
		}
		for _, k := range d.PrimaryKey {
			if d.column(k) == nil {
				problems = append(problems, fmt.Sprintf("%s: primary_key column %s is not declared", d.Name, k))
			}
		}
		for _, c := range d.Columns {
			at := d.Name + "." + c.Name
			if !contains(dataTypes, c.Type) {
				problems = append(problems, fmt.Sprintf("%s: type must be one of %s", at, strings.Join(dataTypes, ", ")))
			}
			if _, ok := c.Nullable.(bool); !ok {
				problems = append(problems, at+": nullable must be true or false")
			}
			if d.Kind == "derived" && len(c.From) == 0 {
				problems = append(problems, at+": a derived column must say what it is built from (from:)")
			}
			if d.Kind == "source" && len(c.From) > 0 {
				problems = append(problems, at+": only derived datasets declare from:")
			}
			for _, src := range c.From {
				t, col, ok := strings.Cut(src, ".")
				if sd := byName[t]; !ok || sd == nil || sd.column(col) == nil {
					problems = append(problems, fmt.Sprintf("%s: from %s is not a declared dataset.column", at, src))
				}
			}
		}
		for _, f := range d.FKs {
			t, col, ok := strings.Cut(f.References, ".")
			if rd := byName[t]; !ok || rd == nil || rd.column(col) == nil {
				problems = append(problems, fmt.Sprintf("%s: foreign key references %s, which is not declared", d.Name, f.References))
			}
			for _, c := range f.Columns {
				if d.column(c) == nil {
					problems = append(problems, fmt.Sprintf("%s: foreign key column %s is not declared", d.Name, c))
				}
			}
		}
	}
	// Lineage must not loop: a dataset can't be built from itself, directly or through others.
	state := map[string]int{}
	var visit func(name string) bool
	visit = func(name string) bool {
		switch state[name] {
		case 1:
			return true
		case 2:
			return false
		}
		state[name] = 1
		if d := byName[name]; d != nil {
			for _, src := range d.sources() {
				t, _, _ := strings.Cut(src, ".")
				if visit(t) {
					state[name] = 2
					return true
				}
			}
		}
		state[name] = 2
		return false
	}
	for _, d := range ds {
		state = map[string]int{}
		if visit(d.Name) {
			problems = append(problems, d.Name+": its lineage loops back to itself")
		}
	}
	return uniqSorted(problems)
}

func nullableStr(v any) string {
	if b, ok := v.(bool); ok {
		if b {
			return "nullable"
		}
		return "not null"
	}
	return "unstated"
}

func fkKeys(d *Dataset) []string {
	var out []string
	for _, f := range d.FKs {
		out = append(out, f.Key())
	}
	return uniqSorted(out)
}

// breakingDataChanges lists what a reader or writer of the old contract would trip over in the new one.
func breakingDataChanges(old, new []*Dataset) []string {
	newBy := datasetsByName(new)
	var out []string
	for _, o := range old {
		n := newBy[o.Name]
		if n == nil {
			out = append(out, o.Name+": dataset removed")
			continue
		}
		if o.Kind != n.Kind {
			out = append(out, fmt.Sprintf("%s: kind changed from %s to %s", o.Name, o.Kind, n.Kind))
		}
		if strings.Join(o.PrimaryKey, ",") != strings.Join(n.PrimaryKey, ",") {
			out = append(out, o.Name+": primary key changed")
		}
		for _, oc := range o.Columns {
			nc := n.column(oc.Name)
			at := o.Name + "." + oc.Name
			if nc == nil {
				out = append(out, at+": column removed")
				continue
			}
			if oc.Type != nc.Type {
				out = append(out, fmt.Sprintf("%s: type changed from %s to %s", at, oc.Type, nc.Type))
			}
			if nullableStr(oc.Nullable) != nullableStr(nc.Nullable) {
				out = append(out, fmt.Sprintf("%s: changed from %s to %s", at, nullableStr(oc.Nullable), nullableStr(nc.Nullable)))
			}
			if strings.Join(uniqSorted(oc.From), ",") != strings.Join(uniqSorted(nc.From), ",") {
				out = append(out, at+": lineage changed")
			}
		}
		for _, nc := range n.Columns {
			if o.column(nc.Name) == nil && nullableStr(nc.Nullable) == "not null" && o.Kind == "source" {
				out = append(out, fmt.Sprintf("%s.%s: new required column on an existing dataset", o.Name, nc.Name))
			}
		}
		nk := fkKeys(n)
		for _, k := range fkKeys(o) {
			if !contains(nk, k) {
				out = append(out, fmt.Sprintf("%s: foreign key %s removed", o.Name, k))
			}
		}
	}
	return out
}

func (e *Engine) checkD4(path string) {
	if e.Base == "" {
		e.add("D4", "project", "data contract", "skip", "No base to compare against", nil)
		return
	}
	oldText, ok := show(e.Repo, e.MergeBase, path)
	if !ok {
		e.add("D4", "project", "data contract", "skip", "No data contract at the base", nil)
		return
	}
	oldDoc, err := loadYAML(oldText)
	if err != nil {
		e.add("D4", "project", "data contract", "skip", "The data contract at the base can't be parsed", nil)
		return
	}
	changes := breakingDataChanges(parseDatasets(oldDoc), e.datasets)
	if len(changes) == 0 {
		e.add("D4", "project", "data contract", "pass", "No breaking data change", nil)
		return
	}
	oldReqs := map[string]string{}
	for _, x := range specAt(e.Repo, e.MergeBase, strList(e.Cfg.Get("specs"))) {
		oldReqs[x.ID] = x.Hash()
	}
	var changed []string
	for _, rid := range e.activeIDs {
		if h, ok := oldReqs[rid]; !ok || h != e.active[rid].Hash() {
			changed = append(changed, rid)
		}
	}
	if len(changed) > 0 {
		e.add("D4", "project", "data contract", "pass",
			fmt.Sprintf("Breaking change allowed: requirement(s) %s changed in the same range", strings.Join(changed, ", ")),
			om("changes", changes))
	} else {
		e.add("D4", "project", "data contract", "fail",
			"Breaking data change with no requirement change: "+shown(changes, 3), om("changes", changes))
	}
}

// observedSchema builds the database the project's own way and reads back what is really there.
func (e *Engine) observedSchema() ([]*Dataset, string) {
	cmd := e.dataCfg().Str("schema_from_code")
	if cmd == "" {
		return nil, "no way to read the database schema for this stack"
	}
	db := filepath.Join(e.Workdir, "schema-check.db")
	for _, suffix := range []string{"", "-wal", "-shm", "-journal"} {
		os.Remove(db + suffix)
	}
	code, out := runShellP(fill(cmd, "db", shQuote(db)), e.Repo, profileEnv(e.Cfg, e.Repo), defaultTimeout,
		pathPairs(e.Repo, e.Workdir))
	line := ""
	ls := splitlines(strip(out))
	for i := len(ls) - 1; i >= 0; i-- {
		if strings.HasPrefix(strip(ls[i]), "{") {
			line = ls[i]
			break
		}
	}
	doc, err := loadJSON([]byte(line))
	if code != 0 || err != nil || line == "" {
		return nil, "couldn't build the database and read its schema: " + tail(strip(out), 300)
	}
	ignore := strList(e.dataCfg().Get("ignore"))
	var kept []*Dataset
	for _, d := range parseDatasets(doc) {
		skip := false
		for _, pat := range ignore {
			if fnmatch(d.Name, pat) {
				skip = true
			}
		}
		if !skip {
			kept = append(kept, d)
		}
	}
	if kept == nil {
		kept = []*Dataset{}
	}
	return kept, ""
}

// schemaProblems compares one declared dataset with what the database has.
func schemaProblems(want, got *Dataset) []string {
	var p []string
	if got.Error != "" {
		return []string{fmt.Sprintf("%s is broken in the database: %s", want.Name, got.Error)}
	}
	if want.Kind == "source" && got.Kind != "table" {
		p = append(p, fmt.Sprintf("%s is a %s, but a source dataset must be a table", want.Name, got.Kind))
	}
	for _, wc := range want.Columns {
		gc := got.column(wc.Name)
		at := want.Name + "." + wc.Name
		if gc == nil {
			p = append(p, at+" is declared but missing from the database")
			continue
		}
		// SQLite gives a view's computed column no type unless the view casts it.
		if gc.Type != wc.Type && !(got.Kind == "view" && gc.Type == "") {
			p = append(p, fmt.Sprintf("%s is %s in the database, %s in the contract", at, gc.Type, wc.Type))
		}
		// A view's columns carry no NOT NULL of their own, so nullability is compared on tables only.
		if got.Kind == "table" && nullableStr(gc.Nullable) != nullableStr(wc.Nullable) {
			p = append(p, fmt.Sprintf("%s is %s in the database, %s in the contract", at, nullableStr(gc.Nullable),
				nullableStr(wc.Nullable)))
		}
	}
	for _, gc := range got.Columns {
		if want.column(gc.Name) == nil {
			p = append(p, fmt.Sprintf("%s.%s is in the database but not in the contract", want.Name, gc.Name))
		}
	}
	if got.Kind == "table" {
		if strings.Join(want.PrimaryKey, ",") != strings.Join(got.PrimaryKey, ",") {
			p = append(p, fmt.Sprintf("%s: primary key is (%s) in the database, (%s) in the contract", want.Name,
				strings.Join(got.PrimaryKey, ", "), strings.Join(want.PrimaryKey, ", ")))
		}
		wk, gk := fkKeys(want), fkKeys(got)
		for _, k := range wk {
			if !contains(gk, k) {
				p = append(p, fmt.Sprintf("%s: foreign key %s is declared but not in the database", want.Name, k))
			}
		}
		for _, k := range gk {
			if !contains(wk, k) {
				p = append(p, fmt.Sprintf("%s: foreign key %s is in the database but not in the contract", want.Name, k))
			}
		}
	}
	return p
}

func (e *Engine) checkD5D6(dataReqs []string) {
	observed, why := e.observedSchema()
	if observed == nil {
		verdict := "error"
		if strings.HasPrefix(why, "no way") {
			verdict = "not_covered"
		}
		for _, c := range []string{"D5", "D6"} {
			e.add(c, "project", "database", verdict, upperFirst(why), nil)
		}
		return
	}
	got := datasetsByName(observed)
	declared := datasetsByName(e.datasets)

	if e.want("D5") {
		for _, d := range observed {
			if declared[d.Name] == nil {
				e.add("D5", "dataset", d.Name, "fail",
					fmt.Sprintf("%s %s is in the database but not in the data contract", upperFirst(d.Kind), d.Name), nil)
			}
		}
		for _, rid := range dataReqs {
			var problems []string
			for _, name := range e.active[rid].DataSets {
				want := declared[name]
				if want == nil {
					continue // D1's problem
				}
				if g := got[name]; g == nil {
					problems = append(problems, name+" is declared but the database doesn't have it")
				} else {
					problems = append(problems, schemaProblems(want, g)...)
				}
			}
			if len(problems) > 0 {
				e.add("D5", "requirement", rid, "fail", shown(problems, 3), om("problems", problems))
			} else {
				e.add("D5", "requirement", rid, "pass", "Its datasets match the contract: "+
					strings.Join(e.active[rid].DataSets, ", "), nil)
			}
		}
	}
	if e.want("D6") {
		e.checkD6(dataReqs, got, declared)
	}
}

func (e *Engine) checkD6(dataReqs []string, got, declared map[string]*Dataset) {
	for _, rid := range dataReqs {
		var derived []*Dataset
		for _, name := range e.active[rid].DataSets {
			if d := declared[name]; d != nil && d.Kind == "derived" {
				derived = append(derived, d)
			}
		}
		if len(derived) == 0 {
			e.add("D6", "requirement", rid, "skip", "No derived dataset", nil)
			continue
		}
		var problems, unseen, names []string
		for _, d := range derived {
			g := got[d.Name]
			if g == nil || g.Error != "" {
				continue // D5's problem
			}
			// A view's definition is in the database, so the engine itself says what it reads. A
			// table is filled by code the verifier can't follow without a per-driver adapter.
			if g.Kind != "view" {
				unseen = append(unseen, d.Name)
				continue
			}
			names = append(names, d.Name)
			problems = append(problems, lineageProblems(d, g.Reads)...)
		}
		problems = uniqSorted(problems)
		switch {
		case len(problems) > 0:
			e.add("D6", "requirement", rid, "fail", shown(problems, 3), om("problems", problems))
		case len(unseen) > 0:
			e.add("D6", "requirement", rid, "not_covered", strings.Join(unseen, ", ")+
				": a derived table's lineage can't be observed; build it as a view", nil)
		case len(names) == 0:
			e.add("D6", "requirement", rid, "skip", "Its derived datasets are not in the database", nil)
		default:
			e.add("D6", "requirement", rid, "pass", "The view definition reads exactly the declared sources: "+
				strings.Join(names, ", "), nil)
		}
	}
}

// lineageProblems compares the columns a derived dataset declares as sources with the ones it reads.
// A read of "t.*" (COUNT(*) and the like) names no column: it is covered by any declared column of t.
func lineageProblems(d *Dataset, seen []string) []string {
	want := d.sources()
	wantTables := map[string]bool{}
	for _, s := range want {
		t, _, _ := strings.Cut(s, ".")
		wantTables[t] = true
	}
	var problems []string
	for _, s := range seen {
		t, col, _ := strings.Cut(s, ".")
		if col == "*" && wantTables[t] {
			continue
		}
		if !contains(want, s) {
			problems = append(problems, fmt.Sprintf("%s reads %s, which its lineage doesn't declare", d.Name, s))
		}
	}
	for _, s := range want {
		if !contains(seen, s) {
			problems = append(problems, fmt.Sprintf("%s declares %s as a source but never reads it", d.Name, s))
		}
	}
	return problems
}

// checkD7: a migration that has reached the base branch is history. Changing it means databases
// built before and after the change differ, so fixes go in a new migration.
func (e *Engine) checkD7() {
	if !e.want("D7") {
		return
	}
	patterns := strList(e.dataCfg().Get("migrations"))
	if len(patterns) == 0 {
		e.add("D7", "project", "migrations", "not_covered", "No data.migrations pattern in .aqv.yml", nil)
		return
	}
	var off []string
	if e.Base != "" {
		out := git(e.Repo, "diff", "--name-status", "--no-renames", e.MergeBase, e.Head)
		for _, l := range splitlines(out) {
			st, path, ok := strings.Cut(l, "\t")
			if ok && st != "A" && len(matching([]string{path}, patterns)) > 0 {
				off = append(off, fmt.Sprintf("%s was %s after it reached %s", path,
					map[string]string{"M": "edited", "D": "deleted"}[head(st, 1)], e.BaseRef))
			}
		}
	} else {
		// On the mainline, each step is one commit or one merged branch: a migration added and
		// reworked inside a branch shows up here as added once.
		out := git(e.Repo, "log", "--first-parent", "-m", "--no-renames", "--name-status", "--format=commit %h", e.Head)
		sha := ""
		for _, l := range splitlines(out) {
			if strings.HasPrefix(l, "commit ") {
				sha = l[7:]
				continue
			}
			st, path, ok := strings.Cut(l, "\t")
			if ok && st != "A" && len(matching([]string{path}, patterns)) > 0 {
				off = append(off, fmt.Sprintf("%s %s %s", sha, map[string]string{"M": "edits", "D": "deletes"}[head(st, 1)], path))
			}
		}
	}
	sort.Strings(off)
	if len(off) > 0 {
		e.add("D7", "project", "migrations", "fail", "Merged migrations changed: "+shown(off, 4), om("offenders", off))
	} else {
		e.add("D7", "project", "migrations", "pass", "No merged migration was edited or deleted", nil)
	}
}

// checkProtected is H10: the spec, the contracts and the verifier's config are the reference the
// agent is checked against, so only people change them.
func (e *Engine) checkProtected() {
	if !e.want(ProtectCheck) {
		return
	}
	g := e.gitCfg()
	humans := strList(g.Get("humans"))
	protected := strList(e.Cfg.Get("protected_paths"))
	var off []string
	for _, cm := range e.rng {
		if cm.IsMerge() || contains(humans, cm.AuthorEmail) {
			continue
		}
		var hit []string
		for _, f := range cm.Files {
			if under(f, protected) {
				hit = append(hit, f)
			}
		}
		if len(hit) > 0 {
			off = append(off, fmt.Sprintf("%s by %s changes %s", cm.Short(), cm.AuthorEmail, strings.Join(hit, ", ")))
		}
	}
	if len(off) > 0 {
		e.add(ProtectCheck, "project", "history", "fail", "Protected files changed by an agent: "+shown(off, 4),
			om("offenders", off))
	} else {
		e.add(ProtectCheck, "project", "history", "pass", "No agent commit changes a protected file", nil)
	}
}

// allCheckIDs is the built-in checks plus any config-dependent ones this run turned on, in report order.
func allCheckIDs(extra []string) []string {
	if len(extra) == 0 {
		return CheckIDs
	}
	var out []string
	for _, fam := range []string{"C", "T", "A", "D", "H"} {
		for _, c := range CheckIDs {
			if strings.HasPrefix(c, fam) {
				out = append(out, c)
			}
		}
		for _, c := range extra {
			if strings.HasPrefix(c, fam) {
				out = append(out, c)
			}
		}
	}
	return out
}

// reportCheckIDs recovers that list from a report, so the renderers need no engine.
func reportCheckIDs(rep *OMap) []string {
	var extra []string
	checks := rep.Map("checks")
	for _, c := range append(append(append([]string{}, DataCheckIDs...), ProtectCheck, OutcomeCheck), ConsistencyCheckIDs...) {
		if checks.Has(c) {
			extra = append(extra, c)
		}
	}
	return allCheckIDs(extra)
}
