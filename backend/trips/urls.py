from django.urls import path

from . import views

urlpatterns = [
    path('health/', views.health, name='health'),
    path('places/', views.places, name='places'),
    path('plan/', views.plan, name='plan'),
]
