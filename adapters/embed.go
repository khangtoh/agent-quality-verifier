// Package adapters holds the files `aqv init` writes into a project.
package adapters

import "embed"

//go:embed init claude/workflows/*.js go/aqvcapture/capture.go
var Files embed.FS
