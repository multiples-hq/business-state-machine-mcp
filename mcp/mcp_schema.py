"""What the agent is sent about a tool's arguments: a lean schema, plain errors.

Two small changes to what the MCP library produces on its own. Neither one
changes which calls are accepted.

The library puts a generated "title" on every parameter, such as "Work Id"
for work_id. It repeats the name and says nothing new, and the agent pays for
the tool list in every session, so the titles are removed.

When arguments do not fit the schema, the library reports the validator's
full dump, with type codes and a documentation link per problem. The agent
gets one line per problem instead: which argument, what is wrong, what was
sent.
"""

from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.tools.base import Tool
from pydantic import ValidationError

SCHEMA_MAPS = ('properties', '$defs')   # keys here are names, not schema words


def without_titles(schema, names=False):
    """The same JSON schema without generated titles. A parameter that is
    itself named title is kept: there the key is a name, not a schema word."""
    if isinstance(schema, list):
        return [without_titles(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    return {key: without_titles(value, names=key in SCHEMA_MAPS and not names)
            for key, value in schema.items()
            if names or key != 'title' or not isinstance(value, str)}


def _place(location):
    """('judgments', 0, 'status') reads as judgments[0].status."""
    text = ''
    for part in location:
        text += f'[{part}]' if isinstance(part, int) else (f'.{part}' if text else str(part))
    return text or 'arguments'


def argument_problems(error):
    """One short line per problem in a failed argument validation."""
    lines = []
    for problem in error.errors(include_url=False, include_context=False):
        sent = repr(problem.get('input'))
        if len(sent) > 80:
            sent = sent[:80] + '...'
        message = problem['msg'].removeprefix('Value error, ')
        lines.append(f'{_place(problem["loc"])}: {message}'
                     + ('' if problem['type'] == 'missing' else f' (got {sent})'))
    return '; '.join(lines)


class PlainTool(Tool):
    """A tool whose argument errors are one line per problem."""

    async def run(self, arguments, context, convert_result=False):
        try:
            return await super().run(arguments, context, convert_result)
        except ToolError as error:
            if isinstance(error.__cause__, ValidationError):
                raise ToolError(f'Error executing tool {self.name}: '
                                f'{argument_problems(error.__cause__)}') from error.__cause__
            raise
