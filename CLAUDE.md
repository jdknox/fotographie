# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands
- `blender --background --factory-startup --addons fotographie --python-expr "import bpy; bpy.ops.lightmeter.measure()"` runs a headless measurement using the add-on (assumes the add-on is enabled and a scene camera exists).
- `blender measure.blend --python-expr "import bpy; bpy.ops.script.reload();"` opens the sample scene and reloads all add-on modules; useful after editing Python files.
- `zip -r ../fotographie.zip fotographie -x "__pycache__/*"` creates a distributable archive for Blender’s extension manager.
- `python -m compileall fotographie` can be used to pre-compile modules and catch syntax errors before loading them in Blender.
- `find . -name "*.py" -exec python -m py_compile {} +` is a quick sanity check for syntax issues without relying on Blender.
- **Legacy modules**: experimental or deprecated variants, such as `_light_meter.py`, are prefixed with an underscore to keep them out of auto-loading while leaving the reference code accessible.

### Styling Conventions
- **No PEP allowed**: Never follow PEP guidelines, only follow house rules.
- **Operator spacing**: multiply/divide/power expressions omit interior spaces (`2*pow`, `pi/2`, `f_stop**2`). Addition and subtraction include spaces on both sides (`a + b`, `ev - 1`). Match this pattern even inside f-strings.
- **Quotes**: prefer single quotes for all string literals, f-strings, and docstrings. Only switch to outside double quotes when syntax requires it (e.g., embedded single quotes).
- **Comparisons**: never use `is`/`is not` for equality. Use `==`/`!=` even when comparing against singletons.
- **Error handling**: avoid `try`/`except`; code should guard upfront instead of relying on exception flow.
- **Attribute access**: prefer direct attribute/property access; avoid `getattr`/`dict.get` unless there is no reasonable alternative.

## Key Development Practices
- Leverage `auto_load` rather than manual `bpy.utils.register_class` calls. Keep `bl_idname` values unique so the dependency sorter can resolve panel hierarchies.
- When defining Blender properties, rely on the `bpy.props` factory functions. `auto_load` parses annotations to infer dependencies; bypassing the factories can break registration order.
Based on Casey Muratori's philosophy, here are concrete Don't/Do examples:

# DON'T/DO for Muratori-style C across all languages:**

## Structure and Organization:**
- ❌ Don't split related code across multiple files/classes for "organization"
- ✅ Do keep related code together in one place you can see at once
- ❌ Don't create deep inheritance hierarchies or abstract base classes
- ✅ Do use simple structs/data with functions that operate on them
- ❌ Don't make one-line wrapper functions for "cleanliness"
- ✅ Do write the actual operation inline where you can see it

## Variables and State:**
- ❌ Don't use `if obj else default`, `getattr(obj, 'name', default)`, `obj?.property`
- ✅ Do use `obj.property` and crash if it's None/null
- ❌ Don't scatter related state across separate variables
- ✅ Do group related state in one struct/object
- ❌ Don't repeat `context.region.x` five times
- ✅ Do store `region = context.region` once, use `region.x` after

## Abstraction and Indirection:**
- ❌ Don't use virtual functions, interfaces, or dynamic dispatch in loops
- ✅ Do use switch/match on a type enum or direct function calls
- ❌ Don't create "flexible" systems that handle unknown future cases
- ✅ Do write code that solves the actual problem you have right now
- ❌ Don't add layers of abstraction "in case we need it later"
- ✅ Do write straightforward code that does the thing directly

## Naming and Readability:**
- ❌ Don't use cryptic abbreviations (`tmp`, `buf`, `ctx` everywhere)
- ✅ Do use descriptive names (`temporary_buffer`, `mouse_position`)
- ❌ Don't make clever one-liners that require mental gymnastics
- ✅ Do write multiple clear lines that read like prose
- ❌ Don't abbreviate to save characters (`calc`, `init`, `proc`)
- ✅ Do spell it out (`calculate`, `initialize`, `process`)

## Error Handling:**
- ❌ Don't wrap everything in try-except or error-checking
- ✅ Do let the program crash on unexpected errors
- ❌ Don't have empty except/catch blocks that hide failures
- ✅ Do fail loud so bugs are immediately visible
- ❌ Don't validate inputs that "should never be wrong"
- ✅ Do assert your assumptions and crash if violated

## Code Size and Complexity:**
- Fine to use simple list comprehensions
- Fine to use slices
- Fine to use `*args` for unpacking
- ❌ Don't extract every operation into a separate function
- ✅ Do keep the code in the function where you can see the whole flow
- ❌ Don't create factory/builder/manager/handler classes
- ✅ Do write a function that does the thing
- ❌ Don't aim for "clever" solutions using advanced language features
- ✅ Do write boring, obvious code that anyone can understand

## Comments:**
- ❌ Don't comment extensively before code is working and stable
- ✅ Do write self-documenting code with clear variable/function names
- ❌ Don't explain what the code does (that should be obvious)
- ✅ Do explain *why* if there's a non-obvious reason

## Performance Mindset:**
- ❌ Don't say "the compiler will optimize it"
- ✅ Do write efficient code from the start (it's not premature optimization)
- ❌ Don't add indirection/abstraction with runtime cost "just in case"
- ✅ Do keep data contiguous and minimize pointer chasing
- ❌ Don't use strings/maps/dictionaries for data that could be arrays/structs
- ✅ Do use simple arrays and direct indexing when possible

## The Core Principle:**
Code should read like what it does. If someone unfamiliar with your codebase reads it, they should understand the actual operations happening, not wade through layers of abstraction to figure out what's really going on.

"Don't use if x else default patterns. Just use x and let it fail if None"
"Don't use getattr(obj, 'name', default). Use obj.name directly"
"Don't check if obj: before accessing it. Access it and crash if it's wrong"
"Store related state in one container object, not separate variables"
"Never write the same variable/attribute name more than once in initialization"

## `null` checks
**Muratori checks for null when it's a *valid state* that the code needs to handle, not as "defensive programming."**

** When to check:**
- ✅ Function takes a pointer that can legitimately be null as part of normal operation
- ✅ Optional data that might not exist (user didn't provide a texture, etc.)
- ✅ Searching/lookup operations that might not find something
- ✅ Allocation that might fail (though he'd probably assert in debug)

** When NOT to check:**
- ❌ "What if this internal state is somehow corrupt?"
- ❌ "What if someone passes bad data?" (that's their bug, let it crash)
- ❌ "What if this initialization didn't work?" (then fix the initialization)
- ❌ Checking the same pointer multiple times after already validating it once

**The distinction:**
- **Valid check**: `if (texture) { use_texture(texture); } else { use_default(); }` - null is expected
- **Defensive junk**: `if (state) { if (state->data) { if (state->data->ptr) { ... }}}` - shouldn't be null

**Rule of thumb:**
If null represents an error in your program's logic, don't check - crash and fix the bug. If null represents a legitimate runtime condition (file not found, optional parameter, etc.), handle it explicitly once at the boundary, then assume valid after that.

Check at the edges where uncertainty enters, not throughout the middle where everything should already be valid.

## Naming Conventions

**Variables:**
- ✅ Do use `snake_case` for all variables (`mouse_position`, `frame_count`)
- ✅ Do use `g_` prefix for module-level globals (`g_state`, `g_counter`)

**Functions:**
- ✅ Do use `camelCase` starting with lowercase for functions (`calculateDistance`, `drawRect`)

**Constants:**
- ✅ Do use `UPPER_SNAKE_CASE` for true constants (`MAX_VERTICES`, `DEFAULT_SIZE`)
- ✅ Do use descriptive names that explain what they represent

**Types/Classes:**
- ✅ Do use `PascalCase` for class/type names (`Vector2D`, `RenderState`)

**Module-level state:**
- ✅ Do prefix with `g_` to show it's global scope
- ✅ Do group related state in a single object rather than many globals

**Example:**
```python
# Constants
MAX_BUTTONS = 10
DEFAULT_FONT_SIZE = 12

# Globals
g_mouse_x = 0
g_active_button = None

# Functions
def calculateDistance(point_a, point_b):
    delta_x = point_b.x - point_a.x
    delta_y = point_b.y - point_a.y
    return math.sqrt(delta_x*delta_x + delta_y*delta_y)

# Classes
class ButtonState:
    pass
```
