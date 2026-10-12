from datetime import datetime

from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import routing, services


class PlaceSerializer(serializers.Serializer):
    """A place the user picked from the autocomplete dropdown."""

    label = serializers.CharField(max_length=200)
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)


class TripRequestSerializer(serializers.Serializer):
    current_location = serializers.CharField(max_length=200)
    pickup_location = serializers.CharField(max_length=200)
    dropoff_location = serializers.CharField(max_length=200)
    cycle_used_hours = serializers.FloatField(min_value=0, max_value=70)
    # Optional: exact places chosen from the dropdown (skips geocoding)
    current_place = PlaceSerializer(required=False, allow_null=True)
    pickup_place = PlaceSerializer(required=False, allow_null=True)
    dropoff_place = PlaceSerializer(required=False, allow_null=True)
    # Optional: local start time of the trip (naive, home-terminal time)
    start_time = serializers.DateTimeField(required=False, allow_null=True)
    # Optional log-sheet details (the header of the paper log)
    driver_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    co_driver = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    carrier_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    main_office = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    home_terminal = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    truck_number = serializers.CharField(max_length=60, required=False, allow_blank=True, default='')
    trailer_number = serializers.CharField(max_length=60, required=False, allow_blank=True, default='')
    shipper = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    commodity = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    shipping_doc = serializers.CharField(max_length=120, required=False, allow_blank=True, default='')


@api_view(['GET'])
def health(request):
    return Response({'status': 'ok'})


@api_view(['GET'])
def places(request):
    """Autocomplete suggestions: GET /api/places/?q=sydn"""
    query = request.query_params.get('q', '')[:100]
    return Response({'results': list(routing.suggest_places(query))})


@api_view(['POST'])
def plan(request):
    serializer = TripRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    start = data.get('start_time')
    if isinstance(start, datetime):
        start = start.replace(tzinfo=None)  # treat as home-terminal local time

    try:
        result = services.plan_trip(
            current=data['current_location'],
            pickup=data['pickup_location'],
            dropoff=data['dropoff_location'],
            cycle_used=data['cycle_used_hours'],
            start=start,
            chosen={
                'current': data.get('current_place'),
                'pickup': data.get('pickup_place'),
                'dropoff': data.get('dropoff_place'),
            },
            details={
                'driver': data['driver_name'],
                'co_driver': data['co_driver'],
                'carrier': data['carrier_name'],
                'office': data['main_office'],
                'home_terminal': data['home_terminal'],
                'truck': data['truck_number'],
                'trailer': data['trailer_number'],
                'shipper': data['shipper'],
                'commodity': data['commodity'],
                'shipping': data['shipping_doc'],
            },
        )
    except routing.RoutingError as exc:
        return Response({'detail': str(exc)}, status=exc.status)
    return Response(result)
