extends RefCounted
## The protocol captures a bounded speed per action; source motion times stay immutable.


static func scaled_us(source_us: int, speed: int) -> int:
	if source_us < 0 or speed < 100 or speed > 170:
		return -1
	# Imported motion offsets are bounded well below int64 overflow.
	@warning_ignore("integer_division")
	return (source_us * 100 + speed - 1) / speed
