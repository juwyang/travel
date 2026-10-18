---
layout: default
title: 旅行日记
---

<section class="home">
  <h1>{{ site.title }}</h1>
  <p class="lede">{{ site.description }}</p>
  <ul class="posts">
  {% assign posts = site.pages | where: 'top', true | sort: 'order' %}
  {% for p in posts %}
    <li><a href="{{ p.url | relative_url }}">{{ p.title }}</a></li>
  {% endfor %}
  </ul>
</section>
