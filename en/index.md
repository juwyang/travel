---
layout: default
title: Travel Notes
---

<section class="home">
  <h1>{{ site.title_en }}</h1>
  <p class="lede">{{ site.description_en }}</p>
  <ul class="posts">
  {% assign posts = site.pages | where: 'top', true | where: 'lang', 'en' | sort: 'order' %}
  {% for p in posts %}
    <li><a href="{{ p.url | relative_url }}">{{ p.title }}</a></li>
  {% endfor %}
  </ul>
</section>
