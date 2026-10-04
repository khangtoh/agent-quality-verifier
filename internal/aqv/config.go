package aqv

// Loads .aqv.yml from the repo under check, filling in defaults (config.py).

const conventional = `^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9._/-]+\))?!?: \S.*$`

var noBehaviorTypes = []string{"refactor", "chore", "style"}

func defaults() *OMap {
	return om(
		"specs", []any{"specs/*.md"},
		"ids_registry", "specs/.ids",
		"contract", "contracts/openapi.yaml",
		"code_paths", []any{"src/"},
		"test_paths", []any{"tests/"},
		"protected_paths", []any{"specs/", ".aqv.yml"},
		"runner", om("broken_exit_codes", []any{}, "comment_prefix", "#"),
		"api", NewOMap(),
		"git", om(
			"humans", []any{},
			"agent_trailer", "Co-Authored-By",
			"branch_pattern", `^(feat|fix|refactor|test|docs|chore)/AC-[a-z0-9]+-[0-9]{3}(-[a-z0-9-]+)?$`,
			"max_commit_lines", int64(400),
			"size_exclude", []any{"*.lock"},
			"verified_ref", "refs/aqv/verified",
		),
		"mutation", om("min_kill_ratio", 0.6, "max_mutants", int64(20)),
	)
}

func mergeConfig(base, extra *OMap) *OMap {
	out := deepCopy(base).(*OMap)
	for _, k := range extra.Keys() {
		v := extra.Get(k)
		if vm, ok := v.(*OMap); ok {
			if bm, ok := out.Get(k).(*OMap); ok {
				out.Set(k, mergeConfig(bm, vm))
				continue
			}
		}
		out.Set(k, v)
	}
	return out
}

// LoadConfig parses .aqv.yml text (empty when the file doesn't exist).
func LoadConfig(text string) (*OMap, error) {
	extra := NewOMap()
	if text != "" {
		v, err := loadYAML(text)
		if err != nil {
			return nil, err
		}
		if m, ok := v.(*OMap); ok {
			extra = m
		}
	}
	return mergeConfig(defaults(), extra), nil
}
