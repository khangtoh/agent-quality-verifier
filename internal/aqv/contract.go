package aqv

// The OpenAPI contract: operations, their requirement links, and response validation
// (contract.py). Response bodies are checked with a JSON Schema 2020-12 subset whose
// messages match the Python jsonschema library.

import (
	"fmt"
	"math"
	"regexp"
	"sort"
	"strings"
	"unicode/utf8"

	"github.com/dlclark/regexp2"
)

var httpMethods = map[string]bool{"get": true, "put": true, "post": true, "delete": true, "patch": true,
	"head": true, "options": true}

type Operation struct {
	Method       string
	Path         string
	Requirements []string
	Responses    *OMap
	pattern      *regexp.Regexp
}

func (o *Operation) Key() string { return o.Method + " " + o.Path }

var escapedParam = regexp.MustCompile(`\\\{[^/]+?\\\}`)

func operations(doc any) []*Operation {
	var ops []*Operation
	d, _ := doc.(*OMap)
	paths := d.Map("paths")
	for _, path := range paths.Keys() {
		item, _ := paths.Get(path).(*OMap)
		for _, method := range item.Keys() {
			op, ok := item.Get(method).(*OMap)
			if !httpMethods[strings.ToLower(method)] || !ok {
				continue
			}
			rx := regexp.MustCompile("^" + escapedParam.ReplaceAllString(regexp.QuoteMeta(path), "[^/]+") + "$")
			resp, _ := op.Get("responses").(*OMap)
			if resp == nil {
				resp = NewOMap()
			}
			ops = append(ops, &Operation{strings.ToUpper(method), path, strList(op.Get("x-requirements")), resp, rx})
		}
	}
	return ops
}

func deref(node, doc any, depth int) any {
	if depth > 50 {
		return node
	}
	switch x := node.(type) {
	case *OMap:
		if ref, ok := x.Get("$ref").(string); ok && strings.HasPrefix(ref, "#/") {
			target := doc
			for _, part := range strings.Split(ref[2:], "/") {
				m, ok := target.(*OMap)
				if !ok || !m.Has(part) {
					panic(fmt.Errorf("KeyError: %s", reprString(part)))
				}
				target = m.Get(part)
			}
			return deref(target, doc, depth+1)
		}
		o := NewOMap()
		for _, k := range x.Keys() {
			o.Set(k, deref(x.Get(k), doc, depth+1))
		}
		return o
	case []any:
		out := make([]any, len(x))
		for i, e := range x {
			out[i] = deref(e, doc, depth+1)
		}
		return out
	}
	return node
}

func findOp(ops []*Operation, method, path string) *Operation {
	for _, op := range ops {
		if op.Method == strings.ToUpper(method) && op.pattern.MatchString(path) {
			return op
		}
	}
	return nil
}

// checkResponse lists problems with one observed response. Empty means it conforms.
func checkResponse(doc any, op *Operation, status any, body any) []string {
	code := pyStr(status)
	var resp *OMap
	for _, k := range []string{code, head(code, 1) + "XX", "default"} {
		if r, ok := op.Responses.Get(k).(*OMap); ok && truthy(r) {
			resp = r
			break
		}
	}
	if resp == nil {
		return []string{fmt.Sprintf("%s returned %s, which the contract doesn't document", op.Key(), code)}
	}
	schema := resp.Map("content").Map("application/json").Get("schema")
	if schema == nil {
		return nil
	}
	var errs []string
	for _, e := range validate(body, deref(schema, doc, 0)) {
		errs = append(errs, fmt.Sprintf("%s %s body breaks the schema: %s", op.Key(), code, e))
	}
	return errs
}

// ---------------------------------------------------------------- JSON Schema subset

func isType(v any, t string) bool {
	switch t {
	case "null":
		return v == nil
	case "boolean":
		_, ok := v.(bool)
		return ok
	case "string":
		_, ok := v.(string)
		return ok
	case "object":
		_, ok := v.(*OMap)
		return ok
	case "array":
		_, ok := v.([]any)
		return ok
	case "integer":
		switch x := v.(type) {
		case int64, int:
			return true
		case float64:
			return x == math.Trunc(x) && !math.IsInf(x, 0)
		}
		return false
	case "number":
		switch v.(type) {
		case int64, int, float64:
			return true
		}
		return false
	}
	return false
}

func jsonEqual(a, b any) bool {
	if ab, ok := a.(bool); ok {
		bb, ok := b.(bool)
		return ok && ab == bb
	}
	if _, ok := b.(bool); ok {
		return false
	}
	if af, ok := toNum(a); ok {
		bf, ok := toNum(b)
		return ok && af == bf
	}
	switch x := a.(type) {
	case nil:
		return b == nil
	case string:
		y, ok := b.(string)
		return ok && x == y
	case []any:
		y, ok := b.([]any)
		if !ok || len(x) != len(y) {
			return false
		}
		for i := range x {
			if !jsonEqual(x[i], y[i]) {
				return false
			}
		}
		return true
	case *OMap:
		y, ok := b.(*OMap)
		if !ok || x.Len() != y.Len() {
			return false
		}
		for _, k := range x.Keys() {
			if !y.Has(k) || !jsonEqual(x.Get(k), y.Get(k)) {
				return false
			}
		}
		return true
	}
	return false
}

func toNum(v any) (float64, bool) {
	switch x := v.(type) {
	case int64:
		return float64(x), true
	case int:
		return float64(x), true
	case float64:
		return x, true
	}
	return 0, false
}

// validate returns error messages in the order Python jsonschema's iter_errors yields them.
func validate(inst, schema any) []string {
	switch s := schema.(type) {
	case bool:
		if s {
			return nil
		}
		return []string{"False schema does not allow " + pyRepr(inst)}
	case *OMap:
		var errs []string
		for _, kw := range s.Keys() {
			errs = append(errs, keyword(kw, s.Get(kw), inst, s)...)
		}
		return errs
	}
	return nil
}

func keyword(kw string, val, inst any, schema *OMap) []string {
	var errs []string
	switch kw {
	case "type":
		types := strList(val)
		for _, t := range types {
			if isType(inst, t) {
				return nil
			}
		}
		reprs := make([]string, len(types))
		for i, t := range types {
			reprs[i] = reprString(t)
		}
		return []string{fmt.Sprintf("%s is not of type %s", pyRepr(inst), strings.Join(reprs, ", "))}
	case "enum":
		list, _ := val.([]any)
		for _, e := range list {
			if jsonEqual(inst, e) {
				return nil
			}
		}
		return []string{fmt.Sprintf("%s is not one of %s", pyRepr(inst), pyRepr(val))}
	case "const":
		if !jsonEqual(inst, val) {
			return []string{pyRepr(val) + " was expected"}
		}
	case "properties":
		obj, ok := inst.(*OMap)
		props, _ := val.(*OMap)
		if !ok {
			return nil
		}
		for _, p := range props.Keys() {
			if obj.Has(p) {
				errs = append(errs, validate(obj.Get(p), props.Get(p))...)
			}
		}
	case "required":
		obj, ok := inst.(*OMap)
		if !ok {
			return nil
		}
		for _, p := range strList(val) {
			if !obj.Has(p) {
				errs = append(errs, reprString(p)+" is a required property")
			}
		}
	case "additionalProperties":
		obj, ok := inst.(*OMap)
		if !ok {
			return nil
		}
		props := schema.Map("properties")
		var pats []string
		for _, k := range schema.Map("patternProperties").Keys() {
			pats = append(pats, k)
		}
		var extras []string
		for _, k := range obj.Keys() {
			if props.Has(k) {
				continue
			}
			if len(pats) > 0 {
				if rx, err := regexp2.Compile(strings.Join(pats, "|"), regexp2.None); err == nil {
					if m, _ := rx.MatchString(k); m {
						continue
					}
				}
			}
			extras = append(extras, k)
		}
		if sub, ok := val.(*OMap); ok {
			for _, k := range extras {
				errs = append(errs, validate(obj.Get(k), sub)...)
			}
		} else if !truthy(val) && len(extras) > 0 {
			sort.Strings(extras)
			reprs := make([]string, len(extras))
			for i, e := range extras {
				reprs[i] = reprString(e)
			}
			if len(pats) > 0 {
				verb := "does"
				if len(extras) != 1 {
					verb = "do"
				}
				sort.Strings(pats)
				pr := make([]string, len(pats))
				for i, p := range pats {
					pr[i] = reprString(p)
				}
				errs = append(errs, fmt.Sprintf("%s %s not match any of the regexes: %s", strings.Join(reprs, ", "), verb,
					strings.Join(pr, ", ")))
			} else {
				verb := "was"
				if len(extras) != 1 {
					verb = "were"
				}
				errs = append(errs, fmt.Sprintf("Additional properties are not allowed (%s %s unexpected)",
					strings.Join(reprs, ", "), verb))
			}
		}
	case "items":
		arr, ok := inst.([]any)
		if !ok {
			return nil
		}
		prefix := 0
		if p, ok := schema.Get("prefixItems").([]any); ok {
			prefix = len(p)
		}
		if len(arr) <= prefix {
			return nil
		}
		if b, ok := val.(bool); ok && !b {
			extra := len(arr) - prefix
			var rest any = arr[prefix:]
			if extra == 1 {
				rest = arr[prefix]
			}
			item := "items"
			if prefix == 1 {
				item = "item"
			}
			return []string{fmt.Sprintf("Expected at most %d %s but found %d extra: %s", prefix, item, extra, pyRepr(rest))}
		}
		for _, e := range arr[prefix:] {
			errs = append(errs, validate(e, val)...)
		}
	case "prefixItems":
		arr, ok := inst.([]any)
		list, _ := val.([]any)
		if !ok {
			return nil
		}
		for i := 0; i < len(arr) && i < len(list); i++ {
			errs = append(errs, validate(arr[i], list[i])...)
		}
	case "minItems", "maxItems":
		arr, ok := inst.([]any)
		n, _ := toFloat(val)
		if !ok {
			return nil
		}
		if kw == "minItems" && float64(len(arr)) < n {
			msg := "is too short"
			if n == 1 {
				msg = "should be non-empty"
			}
			return []string{pyRepr(inst) + " " + msg}
		}
		if kw == "maxItems" && float64(len(arr)) > n {
			msg := "is too long"
			if n == 0 {
				msg = "is expected to be empty"
			}
			return []string{pyRepr(inst) + " " + msg}
		}
	case "minLength", "maxLength":
		s, ok := inst.(string)
		n, _ := toFloat(val)
		if !ok {
			return nil
		}
		l := float64(utf8.RuneCountInString(s))
		if kw == "minLength" && l < n {
			msg := "is too short"
			if n == 1 {
				msg = "should be non-empty"
			}
			return []string{pyRepr(inst) + " " + msg}
		}
		if kw == "maxLength" && l > n {
			msg := "is too long"
			if n == 0 {
				msg = "is expected to be empty"
			}
			return []string{pyRepr(inst) + " " + msg}
		}
	case "pattern":
		s, ok := inst.(string)
		p, _ := val.(string)
		if !ok {
			return nil
		}
		if rx, err := regexp2.Compile(p, regexp2.None); err == nil {
			if m, _ := rx.MatchString(s); !m {
				return []string{fmt.Sprintf("%s does not match %s", pyRepr(inst), reprString(p))}
			}
		}
	case "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum":
		x, ok := toNum(inst)
		if _, isBool := inst.(bool); isBool || !ok {
			return nil
		}
		lim, ok := toNum(val)
		if !ok {
			return nil
		}
		switch {
		case kw == "minimum" && x < lim:
			return []string{fmt.Sprintf("%s is less than the minimum of %s", pyRepr(inst), pyRepr(val))}
		case kw == "maximum" && x > lim:
			return []string{fmt.Sprintf("%s is greater than the maximum of %s", pyRepr(inst), pyRepr(val))}
		case kw == "exclusiveMinimum" && x <= lim:
			return []string{fmt.Sprintf("%s is less than or equal to the minimum of %s", pyRepr(inst), pyRepr(val))}
		case kw == "exclusiveMaximum" && x >= lim:
			return []string{fmt.Sprintf("%s is greater than or equal to the maximum of %s", pyRepr(inst), pyRepr(val))}
		}
	case "allOf":
		list, _ := val.([]any)
		for _, sub := range list {
			errs = append(errs, validate(inst, sub)...)
		}
	case "anyOf":
		list, _ := val.([]any)
		for _, sub := range list {
			if len(validate(inst, sub)) == 0 {
				return nil
			}
		}
		return []string{pyRepr(inst) + " is not valid under any of the given schemas"}
	case "oneOf":
		list, _ := val.([]any)
		var valid []any
		for _, sub := range list {
			if len(validate(inst, sub)) == 0 {
				valid = append(valid, sub)
			}
		}
		if len(valid) == 0 {
			return []string{pyRepr(inst) + " is not valid under any of the given schemas"}
		}
		if len(valid) > 1 {
			reprs := make([]string, len(valid))
			for i, v := range valid {
				reprs[i] = pyRepr(v)
			}
			return []string{pyRepr(inst) + " is valid under each of " + strings.Join(reprs, ", ")}
		}
	case "not":
		if len(validate(inst, val)) == 0 {
			return []string{fmt.Sprintf("%s should not be valid under %s", pyRepr(inst), pyRepr(val))}
		}
	}
	return errs
}
