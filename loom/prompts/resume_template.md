# {{ candidate.name }}

{{ candidate.email }}
{%- if candidate.phone %} | {{ candidate.phone }}{% endif %}
{%- if candidate.linkedin %} | [LinkedIn]({{ candidate.linkedin }}){% endif %}
{%- if candidate.github %} | [GitHub]({{ candidate.github }}){% endif %}
{%- if candidate.location %} | {{ candidate.location }}{% endif %}

## Technical Skills
{% for skill_group in skills %}
- **{{ skill_group.category }}:** {{ skill_group.content }}
{%- endfor %}

## Education
{% for edu in education %}
**{{ edu.degree }}** — {{ edu.institution }} *{{ edu.period }}*
{% endfor %}

{%- if certifications %}

## Certifications
{% for cert in certifications %}
- {{ cert.year }}, {{ cert.name }}
{%- endfor %}
{%- endif %}

## Experience
{% for exp in experiences %}
### {{ exp.title }} — {{ exp.company }}
*{{ exp.period }}*
{% for bullet in exp.bullets %}
- {{ bullet }}
{%- endfor %}
{% endfor %}

{%- if projects %}

## Projects
{% for proj in projects %}
### {{ proj.name }}{% if proj.tech_stack %} — *{{ proj.tech_stack | join(', ') }}*{% endif %}
{% for bullet in proj.bullets %}
- {{ bullet }}
{%- endfor %}
{% endfor %}
{%- endif %}
