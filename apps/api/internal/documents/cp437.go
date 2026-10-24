package documents

// cp437High are the characters of bytes 0x80 to 0xFF in code page 437, the
// encoding of ZIP entry names written without the UTF-8 flag.
const cp437High = "ÇüéâäàåçêëèïîìÄÅÉæÆôöòûùÿÖÜ¢£¥₧ƒáíóúñÑªº¿⌐¬½¼¡«»░▒▓│┤╡╢╖╕╣║╗╝╜╛┐└┴┬├─┼╞╟╚╔╩╦╠═╬╧╨╤╥╙╘╒╓╫╪┘┌█▄▌▐▀αßΓπΣσµτΦΘΩδ∞φε∩≡±≥≤⌠⌡÷≈°∙·√ⁿ²■\u00a0"

// decodeCP437 decodes a name stored in code page 437.
func decodeCP437(raw string) string {
	high := []rune(cp437High)
	decoded := make([]rune, 0, len(raw))
	for i := 0; i < len(raw); i++ {
		if b := raw[i]; b < 0x80 {
			decoded = append(decoded, rune(b))
		} else {
			decoded = append(decoded, high[b-0x80])
		}
	}
	return string(decoded)
}
