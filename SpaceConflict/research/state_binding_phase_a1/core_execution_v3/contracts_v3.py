"""Public templates only; no hidden values or truth-dependent output contracts."""
SYSTEM = ('Answer the specified query using only the supplied evidence and any explicitly stated hypothetical intervention. '
          'A candidate statement is a claim to evaluate, not evidence that it is true. Return one JSON object without an '
          'explanation or Markdown. Follow the stated evidence scope and output format. Do not exceed 512 generated tokens.')
SCALAR = ('Return exactly one JSON object with the single key "value".\n'
          'For a count, use a nonnegative JSON integer when the requested exact value is uniquely determined by the '
          'supplied evidence. Otherwise use JSON null.\n'
          'Zero is a count, not a synonym for unavailable information. Do not use a status key, quoted numbers, or extra keys.')
LABEL = ('SUPPORTED means the supplied evidence establishes this statement in the specified target. '
         'CONTRADICTORY means it establishes an incompatible fact or the statement\'s negation. '
         'UNKNOWN means neither is established from the supplied evidence. '
         'Return exactly one JSON object with the single key "label" and one of SUPPORTED, CONTRADICTORY, UNKNOWN.')
ACTION = ('Report the operation, the affected category or explicitly identified target, and the number of affected '
          'instances stated or uniquely determined by this intervention. Use keys "operation", "target", and "amount". '
          'operation must be ADD or REMOVE, or null if unresolved. Use null for a field that cannot be resolved from '
          'the supplied evidence. Do not invent an object identifier or an amount.')
VALUE_SCHEMA = dict(kind='value', domain='count', nullable=True)
ACTION_SCHEMA = dict(kind='action', nullable=True, operations=['ADD','REMOVE'])


def joint_text(keys):
    names = ['PRE','POST'] if set(keys)=={'PRE','POST'} else sorted(keys)
    return ('Report the query count separately for each named key. Write the entries in this order: ' + ', '.join(keys) +
            '.\nReturn one JSON object keyed by ' + ' and '.join(names) + '. Each value must be a nonnegative JSON integer '
            'if uniquely determined, or null otherwise. Do not add nested status objects or explanations.')


def table_header(query):
    return ('This is a controlled text-only task. The following rows are the available facts.\n'
            '"query_count" denotes exactly: ' + query + '.\n'
            '"unrelated_register" is a different variable and is not the requested count.\n'
            'Rows are state-indexed records. Do not transfer a value to another state without an explicitly supplied rule. '
            'No cross-state transition rule is supplied here.\n')
