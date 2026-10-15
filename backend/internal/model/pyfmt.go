package model

import (
	"math"
	"math/big"
	"strconv"
	"strings"

	"github.com/shopspring/decimal"
)

// FormatFloat formats f like Python's repr(float) / str(float): the shortest round-tripping
// digits, always with a decimal point or exponent ("18.0", "0.1", "1e-05", "1e+16").
func FormatFloat(f float64) string {
	switch {
	case math.IsNaN(f):
		return "nan"
	case math.IsInf(f, 1):
		return "inf"
	case math.IsInf(f, -1):
		return "-inf"
	}
	s := strconv.FormatFloat(f, 'e', -1, 64)
	sign := ""
	if s[0] == '-' {
		sign, s = "-", s[1:]
	}
	mant, expStr, _ := strings.Cut(s, "e")
	exp, _ := strconv.Atoi(expStr)
	digits := strings.Replace(mant, ".", "", 1)
	decpt := exp + 1
	if decpt < -3 || decpt > 16 {
		out := digits[:1]
		if len(digits) > 1 {
			out += "." + digits[1:]
		}
		e := exp
		esign := "+"
		if e < 0 {
			esign, e = "-", -e
		}
		es := strconv.Itoa(e)
		if len(es) < 2 {
			es = "0" + es
		}
		return sign + out + "e" + esign + es
	}
	switch {
	case decpt <= 0:
		return sign + "0." + strings.Repeat("0", -decpt) + digits
	case decpt >= len(digits):
		return sign + digits + strings.Repeat("0", decpt-len(digits)) + ".0"
	default:
		return sign + digits[:decpt] + "." + digits[decpt:]
	}
}

// FormatG formats f like Python's format(f, "g") (6 significant digits, trailing zeros removed).
func FormatG(f float64) string {
	switch {
	case math.IsNaN(f):
		return "nan"
	case math.IsInf(f, 1):
		return "inf"
	case math.IsInf(f, -1):
		return "-inf"
	}
	return strconv.FormatFloat(f, 'g', 6, 64)
}

var bigTen = big.NewInt(10)

func pow10(n int) *big.Int {
	return new(big.Int).Exp(bigTen, big.NewInt(int64(n)), nil)
}

// FormatDecimal formats d like Python's str(Decimal): the exponent is kept ("179.00"), very
// small or large exponents use scientific notation ("1E+2", "1E-7").
func FormatDecimal(d decimal.Decimal) string {
	coef := d.Coefficient()
	exp := int(d.Exponent())
	sign := ""
	if coef.Sign() < 0 {
		sign = "-"
		coef.Neg(coef)
	}
	c := coef.String()
	leftdigits := exp + len(c)
	var dotplace int
	if exp <= 0 && leftdigits > -6 {
		dotplace = leftdigits
	} else {
		dotplace = 1
	}
	var intpart, fracpart string
	switch {
	case dotplace <= 0:
		intpart = "0"
		fracpart = "." + strings.Repeat("0", -dotplace) + c
	case dotplace >= len(c):
		intpart = c + strings.Repeat("0", dotplace-len(c))
	default:
		intpart = c[:dotplace]
		fracpart = "." + c[dotplace:]
	}
	expPart := ""
	if leftdigits != dotplace {
		e := leftdigits - dotplace
		if e >= 0 {
			expPart = "E+" + strconv.Itoa(e)
		} else {
			expPart = "E" + strconv.Itoa(e)
		}
	}
	return sign + intpart + fracpart + expPart
}

// DecimalFromFloat converts like Python's Decimal(str(f)): the shortest repr of the float.
func DecimalFromFloat(f float64) decimal.Decimal {
	d, err := decimal.NewFromString(FormatFloat(f))
	if err != nil {
		return decimal.NewFromFloat(f)
	}
	return d
}

// ParseDecimal parses a decimal string like Python's Decimal(s.strip()), keeping the exponent.
// Non-finite values (NaN, Infinity) are rejected.
func ParseDecimal(s string) (decimal.Decimal, error) {
	return decimal.NewFromString(strings.ReplaceAll(strings.TrimSpace(s), "_", ""))
}

func roundCoef(d decimal.Decimal, places int32, halfEven bool) decimal.Decimal {
	exp := d.Exponent()
	coef := d.Coefficient()
	if exp >= -places {
		coef.Mul(coef, pow10(int(exp+places)))
		return decimal.NewFromBigInt(coef, -places)
	}
	div := pow10(int(-places - exp))
	neg := coef.Sign() < 0
	coef.Abs(coef)
	q, r := new(big.Int).QuoRem(coef, div, new(big.Int))
	r2 := new(big.Int).Lsh(r, 1)
	cmp := r2.Cmp(div)
	if cmp > 0 || (cmp == 0 && (!halfEven || q.Bit(0) == 1)) {
		q.Add(q, big.NewInt(1))
	}
	if neg {
		q.Neg(q)
	}
	return decimal.NewFromBigInt(q, -places)
}

// QuantizeHalfUp is Python's d.quantize(Decimal(10) ** -places, ROUND_HALF_UP): round half away
// from zero to exactly `places` decimal places (the exponent of the result is -places).
func QuantizeHalfUp(d decimal.Decimal, places int32) decimal.Decimal {
	return roundCoef(d, places, false)
}

// QuantizeHalfEven is Python's d.quantize(Decimal(10) ** -places) with the default
// ROUND_HALF_EVEN rounding.
func QuantizeHalfEven(d decimal.Decimal, places int32) decimal.Decimal {
	return roundCoef(d, places, true)
}

// DecimalPrecision is the precision of Python's default decimal context.
const DecimalPrecision = 28

// DivDecimal divides like Python's Decimal a / b in the default context (28 significant digits,
// ROUND_HALF_EVEN, exact results reduced towards the ideal exponent). It panics on b == 0, as
// Python raises DivisionByZero.
func DivDecimal(a, b decimal.Decimal) decimal.Decimal {
	cb := b.Coefficient()
	if cb.Sign() == 0 {
		panic("model.DivDecimal: division by zero")
	}
	ca := a.Coefficient()
	neg := (ca.Sign() < 0) != (cb.Sign() < 0)
	ca.Abs(ca)
	cb.Abs(cb)
	idealExp := int(a.Exponent()) - int(b.Exponent())
	if ca.Sign() == 0 {
		return decimal.NewFromBigInt(big.NewInt(0), int32(idealExp))
	}
	shift := len(cb.String()) - len(ca.String()) + DecimalPrecision + 1
	exp := idealExp - shift
	var q, r big.Int
	if shift >= 0 {
		q.QuoRem(new(big.Int).Mul(ca, pow10(shift)), cb, &r)
	} else {
		q.QuoRem(ca, new(big.Int).Mul(cb, pow10(-shift)), &r)
	}
	five := big.NewInt(5)
	if r.Sign() != 0 {
		// Sticky digit so that the final rounding sees the inexact remainder.
		if new(big.Int).Mod(&q, five).Sign() == 0 {
			q.Add(&q, big.NewInt(1))
		}
	} else {
		ten := big.NewInt(10)
		var m big.Int
		for exp < idealExp {
			if m.Mod(&q, ten).Sign() != 0 {
				break
			}
			q.Quo(&q, ten)
			exp++
		}
	}
	// Round the coefficient to DecimalPrecision digits (ROUND_HALF_EVEN).
	if n := len(q.String()); n > DecimalPrecision {
		drop := n - DecimalPrecision
		rounded := roundCoef(decimal.NewFromBigInt(&q, 0), -int32(drop), true)
		c := rounded.Coefficient()
		exp += drop
		if len(c.String()) > DecimalPrecision {
			c.Quo(c, big.NewInt(10))
			exp++
		}
		q = *c
	}
	if neg {
		q.Neg(&q)
	}
	return decimal.NewFromBigInt(&q, int32(exp))
}
