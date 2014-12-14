import pint

units = pint.UnitRegistry()

def unit( string, u = None ):
  v = units.parse_expression( string )
  if u is not None:
    if u.dimensionality != v.dimensionality:
      # if v does not have the same dimensions as u, throw away the units of v and assume it has the same units as u
      v = (u / u.magnitude) * v.magnitude

  return v
