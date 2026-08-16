# {{ candidate.name }}

{{ candidate.email }}
{%- if candidate.phone %} | {{ candidate.phone }}{% endif %}
{%- if candidate.linkedin %} | [LinkedIn]({{ candidate.linkedin }}){% endif %}
{%- if candidate.github %} | [GitHub]({{ candidate.github }}){% endif %}
{%- if candidate.location %} | {{ candidate.location }}{% endif %}

## 专业技能
{% for skill_group in skills %}
- **{{ skill_group.category }}:** {{ skill_group.content }}
{%- endfor %}

## 工作经历
{% for exp in experiences %}
### {{ exp.title }} — {{ exp.company }}
*{{ exp.period }}*{%- if exp.location %} | *{{ exp.location }}*{% endif %}
{% for bullet in exp.bullets %}
- {{ bullet }}
{%- endfor %}
{% endfor %}

{%- if projects %}

## 项目经历
{% for proj in projects %}
### {{ proj.name }}{% if proj.tech_stack %} — *{{ proj.tech_stack | join(', ') }}*{% endif %}
{% for bullet in proj.bullets %}
- {{ bullet }}
{%- endfor %}
{% endfor %}
{%- endif %}

## 教育背景
{% for edu in education %}
**{{ edu.degree }}** — {{ edu.institution }} *{{ edu.period }}*
{% endfor %}

{%- if certifications %}

## 证书与奖项
{% for cert in certifications %}
- {{ cert.year }}, {{ cert.name }}
{%- endfor %}
{%- endif %}
