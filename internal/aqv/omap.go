package aqv

// OMap is an insertion-ordered map, the Go stand-in for a Python dict. YAML and
// JSON documents are decoded into OMap, []any, string, int64, float64, bool and nil,
// and reports are written with dumpJSON, which matches Python's json.dump(indent=2).

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"strconv"
	"strings"

	"gopkg.in/yaml.v3"
)

type OMap struct {
	keys []string
	m    map[string]any
}

func NewOMap() *OMap { return &OMap{m: map[string]any{}} }

// om builds an OMap from alternating keys and values.
func om(kv ...any) *OMap {
	o := NewOMap()
	for i := 0; i+1 < len(kv); i += 2 {
		o.Set(kv[i].(string), kv[i+1])
	}
	return o
}

func (o *OMap) Set(k string, v any) {
	if _, ok := o.m[k]; !ok {
		o.keys = append(o.keys, k)
	}
	o.m[k] = v
}

func (o *OMap) Get(k string) any {
	if o == nil {
		return nil
	}
	return o.m[k]
}

func (o *OMap) Has(k string) bool {
	if o == nil {
		return false
	}
	_, ok := o.m[k]
	return ok
}

func (o *OMap) Delete(k string) {
	if _, ok := o.m[k]; !ok {
		return
	}
	delete(o.m, k)
	for i, x := range o.keys {
		if x == k {
			o.keys = append(o.keys[:i], o.keys[i+1:]...)
			break
		}
	}
}

func (o *OMap) Keys() []string {
	if o == nil {
		return nil
	}
	return o.keys
}

func (o *OMap) Len() int {
	if o == nil {
		return 0
	}
	return len(o.keys)
}

// Map returns the value at k when it is a mapping.
func (o *OMap) Map(k string) *OMap {
	v, _ := o.Get(k).(*OMap)
	return v
}

// Str returns the value at k when it is a string (Python's d.get(k, "")).
func (o *OMap) Str(k string) string {
	switch v := o.Get(k).(type) {
	case string:
		return v
	case nil:
		return ""
	default:
		return pyStr(v)
	}
}

func (o *OMap) Truthy(k string) bool { return truthy(o.Get(k)) }

func truthy(v any) bool {
	switch x := v.(type) {
	case nil:
		return false
	case bool:
		return x
	case string:
		return x != ""
	case int64:
		return x != 0
	case int:
		return x != 0
	case float64:
		return x != 0
	case []any:
		return len(x) > 0
	case *OMap:
		return x.Len() > 0
	}
	return true
}

func strList(v any) []string {
	switch x := v.(type) {
	case []any:
		out := make([]string, 0, len(x))
		for _, e := range x {
			out = append(out, pyStr(e))
		}
		return out
	case []string:
		return x
	case string:
		return []string{x}
	}
	return nil
}

func intList(v any) []int {
	var out []int
	if xs, ok := v.([]any); ok {
		for _, e := range xs {
			if n, ok := toFloat(e); ok {
				out = append(out, int(n))
			}
		}
	}
	return out
}

func toFloat(v any) (float64, bool) {
	switch x := v.(type) {
	case int64:
		return float64(x), true
	case int:
		return float64(x), true
	case float64:
		return x, true
	case string:
		f, err := strconv.ParseFloat(x, 64)
		return f, err == nil
	}
	return 0, false
}

func deepCopy(v any) any {
	switch x := v.(type) {
	case *OMap:
		o := NewOMap()
		for _, k := range x.keys {
			o.Set(k, deepCopy(x.m[k]))
		}
		return o
	case []any:
		out := make([]any, len(x))
		for i, e := range x {
			out[i] = deepCopy(e)
		}
		return out
	}
	return v
}

// ---------------------------------------------------------------- YAML

// loadYAML decodes text like yaml.safe_load, keeping mapping order. Empty input gives nil.
func loadYAML(text string) (any, error) {
	var n yaml.Node
	if err := yaml.Unmarshal([]byte(text), &n); err != nil {
		return nil, err
	}
	if n.Kind == 0 || len(n.Content) == 0 {
		return nil, nil
	}
	return fromNode(n.Content[0])
}

func fromNode(n *yaml.Node) (any, error) {
	switch n.Kind {
	case yaml.AliasNode:
		return fromNode(n.Alias)
	case yaml.MappingNode:
		o := NewOMap()
		for i := 0; i+1 < len(n.Content); i += 2 {
			k, v := n.Content[i], n.Content[i+1]
			if k.Tag == "!!merge" {
				src := v
				if src.Kind == yaml.AliasNode {
					src = src.Alias
				}
				mv, err := fromNode(src)
				if err != nil {
					return nil, err
				}
				if mm, ok := mv.(*OMap); ok {
					for _, mk := range mm.keys {
						if !o.Has(mk) {
							o.Set(mk, mm.m[mk])
						}
					}
				}
				continue
			}
			key := k.Value
			if k.Kind == yaml.AliasNode {
				key = k.Alias.Value
			}
			val, err := fromNode(v)
			if err != nil {
				return nil, err
			}
			o.Set(key, val)
		}
		return o, nil
	case yaml.SequenceNode:
		out := make([]any, 0, len(n.Content))
		for _, c := range n.Content {
			v, err := fromNode(c)
			if err != nil {
				return nil, err
			}
			out = append(out, v)
		}
		return out, nil
	case yaml.ScalarNode:
		var v any
		if err := n.Decode(&v); err != nil {
			return nil, err
		}
		switch x := v.(type) {
		case int:
			return int64(x), nil
		case uint64:
			return float64(x), nil
		}
		return v, nil
	}
	return nil, nil
}

// ---------------------------------------------------------------- JSON in

// loadJSON decodes JSON keeping object key order; integers stay int64.
func loadJSON(data []byte) (any, error) {
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.UseNumber()
	v, err := decodeValue(dec)
	if err != nil {
		return nil, err
	}
	if _, err := dec.Token(); err != io.EOF {
		return nil, fmt.Errorf("extra data after JSON value")
	}
	return v, nil
}

func decodeValue(dec *json.Decoder) (any, error) {
	t, err := dec.Token()
	if err != nil {
		return nil, err
	}
	switch x := t.(type) {
	case json.Delim:
		switch x {
		case '{':
			o := NewOMap()
			for dec.More() {
				kt, err := dec.Token()
				if err != nil {
					return nil, err
				}
				k, _ := kt.(string)
				v, err := decodeValue(dec)
				if err != nil {
					return nil, err
				}
				o.Set(k, v)
			}
			if _, err := dec.Token(); err != nil {
				return nil, err
			}
			return o, nil
		case '[':
			out := []any{}
			for dec.More() {
				v, err := decodeValue(dec)
				if err != nil {
					return nil, err
				}
				out = append(out, v)
			}
			if _, err := dec.Token(); err != nil {
				return nil, err
			}
			return out, nil
		}
	case json.Number:
		s := x.String()
		if !strings.ContainsAny(s, ".eE") {
			if n, err := strconv.ParseInt(s, 10, 64); err == nil {
				return n, nil
			}
		}
		f, err := strconv.ParseFloat(s, 64)
		return f, err
	case string, bool, nil:
		return x, nil
	}
	return nil, fmt.Errorf("unexpected JSON token %v", t)
}

// ---------------------------------------------------------------- JSON out

// dumpJSON writes v like Python's json.dump(v, indent=2): ASCII-only, ": " and ","
// separators, floats as repr().
func dumpJSON(v any) string {
	var b strings.Builder
	writeJSON(&b, v, 0)
	return b.String()
}

func writeJSON(b *strings.Builder, v any, depth int) {
	ind := func(d int) string { return "\n" + strings.Repeat("  ", d) }
	switch x := v.(type) {
	case nil:
		b.WriteString("null")
	case bool:
		if x {
			b.WriteString("true")
		} else {
			b.WriteString("false")
		}
	case string:
		writeJSONString(b, x)
	case int:
		b.WriteString(strconv.Itoa(x))
	case int64:
		b.WriteString(strconv.FormatInt(x, 10))
	case float64:
		b.WriteString(pyFloat(x))
	case []string:
		arr := make([]any, len(x))
		for i, s := range x {
			arr[i] = s
		}
		writeJSON(b, arr, depth)
	case []int:
		arr := make([]any, len(x))
		for i, n := range x {
			arr[i] = n
		}
		writeJSON(b, arr, depth)
	case []any:
		if len(x) == 0 {
			b.WriteString("[]")
			return
		}
		b.WriteString("[")
		for i, e := range x {
			if i > 0 {
				b.WriteString(",")
			}
			b.WriteString(ind(depth + 1))
			writeJSON(b, e, depth+1)
		}
		b.WriteString(ind(depth) + "]")
	case *OMap:
		if x.Len() == 0 {
			b.WriteString("{}")
			return
		}
		b.WriteString("{")
		for i, k := range x.keys {
			if i > 0 {
				b.WriteString(",")
			}
			b.WriteString(ind(depth + 1))
			writeJSONString(b, k)
			b.WriteString(": ")
			writeJSON(b, x.m[k], depth+1)
		}
		b.WriteString(ind(depth) + "}")
	default:
		writeJSONString(b, fmt.Sprint(x))
	}
}

func writeJSONString(b *strings.Builder, s string) {
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			b.WriteString(`\"`)
		case '\\':
			b.WriteString(`\\`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		case '\b':
			b.WriteString(`\b`)
		case '\f':
			b.WriteString(`\f`)
		default:
			if r < 0x20 || r > 0x7e {
				if r > 0xffff {
					r -= 0x10000
					fmt.Fprintf(b, `\u%04x\u%04x`, 0xd800+(r>>10), 0xdc00+(r&0x3ff))
				} else {
					fmt.Fprintf(b, `\u%04x`, r)
				}
			} else {
				b.WriteRune(r)
			}
		}
	}
	b.WriteByte('"')
}
