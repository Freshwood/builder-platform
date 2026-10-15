package model

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"strings"
)

type nodeKind uint8

const (
	nNull nodeKind = iota
	nBool
	nNumber
	nString
	nArray
	nObject
)

// node is a parsed JSON value that keeps object key order and the literal text of numbers.
type node struct {
	kind nodeKind
	b    bool
	s    string // string value or number literal
	arr  []*node
	keys []string
	vals []*node
}

func (n *node) get(key string) (*node, bool) {
	for i, k := range n.keys {
		if k == key {
			return n.vals[i], true
		}
	}
	return nil, false
}

// isIntLiteral reports whether a number literal has no fraction and no exponent.
func (n *node) isIntLiteral() bool {
	return n.kind == nNumber && !strings.ContainsAny(n.s, ".eE")
}

func parseNode(data []byte) (*node, error) {
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.UseNumber()
	n, err := readNode(dec)
	if err != nil {
		return nil, err
	}
	if _, err := dec.Token(); err != io.EOF {
		return nil, fmt.Errorf("trailing data after JSON value")
	}
	return n, nil
}

func readNode(dec *json.Decoder) (*node, error) {
	tok, err := dec.Token()
	if err != nil {
		return nil, err
	}
	return nodeFromToken(dec, tok)
}

func nodeFromToken(dec *json.Decoder, tok json.Token) (*node, error) {
	switch t := tok.(type) {
	case nil:
		return &node{kind: nNull}, nil
	case bool:
		return &node{kind: nBool, b: t}, nil
	case json.Number:
		return &node{kind: nNumber, s: string(t)}, nil
	case string:
		return &node{kind: nString, s: t}, nil
	case json.Delim:
		switch t {
		case '[':
			n := &node{kind: nArray, arr: []*node{}}
			for dec.More() {
				child, err := readNode(dec)
				if err != nil {
					return nil, err
				}
				n.arr = append(n.arr, child)
			}
			if _, err := dec.Token(); err != nil {
				return nil, err
			}
			return n, nil
		case '{':
			n := &node{kind: nObject}
			index := map[string]int{}
			for dec.More() {
				ktok, err := dec.Token()
				if err != nil {
					return nil, err
				}
				key, ok := ktok.(string)
				if !ok {
					return nil, fmt.Errorf("invalid object key")
				}
				child, err := readNode(dec)
				if err != nil {
					return nil, err
				}
				// Duplicate keys: the last value wins, the position of the first stays.
				if i, dup := index[key]; dup {
					n.vals[i] = child
					continue
				}
				index[key] = len(n.keys)
				n.keys = append(n.keys, key)
				n.vals = append(n.vals, child)
			}
			if _, err := dec.Token(); err != nil {
				return nil, err
			}
			return n, nil
		}
	}
	return nil, fmt.Errorf("unexpected JSON token %v", tok)
}
