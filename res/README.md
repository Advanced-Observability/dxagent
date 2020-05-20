# Diagnostic Agent Ressources

* `fields.csv`
   An informative list of vendor-specific monitored fields.
   
* `kpi.csv`
   A list of vendor-independent Key Performance Indicators (KPIs).

* `rules.csv`
   A list of symptoms.
   
## `fields.csv`

This file contains a list of vendor-specific input fields. Each field is described
by the following attributes: category, name, type (e.g., str, int or float), 
counter (1 if the field is a counter, 0 if it is not), unit, and index (e.g.,
how this field is indexed).

`fields.csv` is purely informative and not used in DxAgent at the moment.

## `kpi.csv`

This file contains a list of KPIs, which are *standardized* vendor-independent
performance indicators fields. Each KPI is defined by the following attributes:
name, type (e.g., str, int or float), is_list (1 if this field is contained in
a list, 0 if it is not) and unit. KPI names follow this syntax: 
`{bm|vm|kb}_{subservice}_NAME`, in which `bm|vm|kb` is the name of the
parent subservice, and `subservice` can be:

* bm: cpu, sensors, disk, mem, proc, net

* vm: cpu, mem, net

* kb: proc, mem, net

`kpi.csv` is used by DxAgent.

## `rules.csv`

This file is the list of symptoms, it is used to determine a subservice health.
Each symptom is defined by a name, (e.g., "Swap volume in use"), a severity (e.g.,
Orange or Red), and a rule. Rules are boolean expressions using KPIs as variables
and the following operators (i,e., similar to Python's):

* `and`, `or` and parentheses (i.e., grouping operators).

* `>`, `<`, `>=`, `<=`, `==`, `!=`

* `any()`, `all()` return `True` if the expression inside returns `True` for
respectively at least one element, and all elements, of the list in which it
is contained (i.e., is_list). For instance, `all(bm_cpu_user_time>95)` is
`True` if all CPUs are 95% busy.

* 1min(), 5min(), 10min() return `True` if the expression inside is `True`
for the given period of time.


If a symptom is superseeding another, its rule should specifically exclude the rule of
the superseeded symptom, and reciprocally.
