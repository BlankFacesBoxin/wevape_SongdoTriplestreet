from django.urls import path
from preview_site import views

urlpatterns = [path('', views.home), path('api/analysis', views.analysis),
               path('app.js', views.asset, {'name': 'app.js'}),
               path('style.css', views.asset, {'name': 'style.css'}),
               path('healthz', views.health)]
