package expr

import "sort"

// closeCutoff is the minimum similarity of difflib.get_close_matches' default.
const closeCutoff = 0.6

// closeMatch is difflib.get_close_matches(word, possibilities, n=1) from Python: the possibility
// most similar to word whose ratio reaches 0.6. Equal scores go to the greater string, like the
// (score, x) tuples Python compares.
func closeMatch(word string, possibilities []string) (string, bool) {
	b := []rune(word)
	idx := newBIndex(b)
	best, found, bestScore := "", false, 0.0
	for _, x := range possibilities {
		a := []rune(x)
		total := len(a) + len(b)
		score := 1.0
		if total > 0 {
			score = 2.0 * float64(idx.matches(a)) / float64(total)
		}
		if score < closeCutoff {
			continue
		}
		if !found || score > bestScore || (score == bestScore && x > best) {
			best, found, bestScore = x, true, score
		}
	}
	return best, found
}

// bIndex is difflib.SequenceMatcher's view of the second sequence: where each element occurs.
// There is no junk function, so only the autojunk heuristic (sequences of 200 or more elements)
// removes elements from the index.
type bIndex struct {
	b   []rune
	b2j map[rune][]int
}

func newBIndex(b []rune) *bIndex {
	idx := &bIndex{b: b, b2j: map[rune][]int{}}
	for j, c := range b {
		idx.b2j[c] = append(idx.b2j[c], j)
	}
	if n := len(b); n >= 200 {
		limit := n/100 + 1
		for c, js := range idx.b2j {
			if len(js) > limit {
				delete(idx.b2j, c)
			}
		}
	}
	return idx
}

// matches is the total size of the matching blocks of a against b (get_matching_blocks).
func (idx *bIndex) matches(a []rune) int {
	type span struct{ alo, ahi, blo, bhi int }
	queue := []span{{0, len(a), 0, len(idx.b)}}
	total := 0
	for len(queue) > 0 {
		q := queue[len(queue)-1]
		queue = queue[:len(queue)-1]
		i, j, k := idx.longestMatch(a, q.alo, q.ahi, q.blo, q.bhi)
		if k == 0 {
			continue
		}
		total += k
		if q.alo < i && q.blo < j {
			queue = append(queue, span{q.alo, i, q.blo, j})
		}
		if i+k < q.ahi && j+k < q.bhi {
			queue = append(queue, span{i + k, q.ahi, j + k, q.bhi})
		}
	}
	return total
}

// longestMatch is SequenceMatcher.find_longest_match without junk: the leftmost longest block
// in a[alo:ahi] and b[blo:bhi], extended over equal neighbours (elements dropped by the
// autojunk heuristic are only found this way).
func (idx *bIndex) longestMatch(a []rune, alo, ahi, blo, bhi int) (besti, bestj, bestsize int) {
	besti, bestj = alo, blo
	j2len := map[int]int{}
	for i := alo; i < ahi; i++ {
		next := map[int]int{}
		js := idx.b2j[a[i]]
		for _, j := range js[sort.SearchInts(js, blo):] {
			if j >= bhi {
				break
			}
			k := j2len[j-1] + 1
			next[j] = k
			if k > bestsize {
				besti, bestj, bestsize = i-k+1, j-k+1, k
			}
		}
		j2len = next
	}
	for besti > alo && bestj > blo && a[besti-1] == idx.b[bestj-1] {
		besti, bestj, bestsize = besti-1, bestj-1, bestsize+1
	}
	for besti+bestsize < ahi && bestj+bestsize < bhi && a[besti+bestsize] == idx.b[bestj+bestsize] {
		bestsize++
	}
	return besti, bestj, bestsize
}
