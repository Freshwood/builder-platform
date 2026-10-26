package expr

import (
	"math"
	"math/big"
	"strconv"
)

// Limits of Python's float round(): beyond them the value is returned unchanged or becomes 0.
const (
	roundMaxDigits = 323  // (DBL_MANT_DIG - DBL_MIN_EXP) * log10(2), truncated
	roundMinDigits = -308 // -(DBL_MAX_EXP + 1) * log10(2), truncated
)

// roundDigits is Python's round(x, ndigits) for a float: round half to even on the exact
// decimal value of x, so round(0.5) is 0, round(2.5) is 2 and round(2.675, 2) is 2.67.
// digits is already truncated to an integer.
func roundDigits(x, digits float64) (float64, error) {
	if math.IsNaN(x) || math.IsInf(x, 0) || x == 0 || digits > roundMaxDigits {
		return x, nil
	}
	if digits < roundMinDigits {
		return math.Copysign(0, x), nil
	}
	nd := int(digits)
	var r float64
	if nd >= 0 {
		// FormatFloat rounds the exact binary value correctly (half to even).
		r, _ = strconv.ParseFloat(strconv.FormatFloat(x, 'f', nd, 64), 64)
	} else {
		r = roundTens(x, -nd)
	}
	if math.IsInf(r, 0) {
		return 0, &OverflowError{Msg: "rounded value too large to represent"}
	}
	return r, nil
}

// roundTens rounds x to a multiple of 10^k (k > 0), half to even, using exact arithmetic.
func roundTens(x float64, k int) float64 {
	scale := new(big.Int).Exp(big.NewInt(10), big.NewInt(int64(k)), nil)
	q := new(big.Rat).SetFloat64(x)
	q.Quo(q, new(big.Rat).SetInt(scale))
	num, den := q.Num(), q.Denom()
	whole, rem := new(big.Int).QuoRem(num, den, new(big.Int))
	// QuoRem truncates toward zero; compare twice the remainder with the denominator.
	twice := new(big.Int).Abs(rem)
	twice.Lsh(twice, 1)
	switch c := twice.Cmp(den); {
	case c > 0, c == 0 && whole.Bit(0) == 1:
		if num.Sign() < 0 {
			whole.Sub(whole, big.NewInt(1))
		} else {
			whole.Add(whole, big.NewInt(1))
		}
	}
	out, _ := new(big.Rat).SetInt(whole.Mul(whole, scale)).Float64()
	if out == 0 {
		return math.Copysign(0, x)
	}
	return out
}
