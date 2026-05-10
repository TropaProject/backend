from rest_framework import serializers
from .models import City, CitySuggestion, Interest, Mood

class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ['id', 'name', 'image_url', 'description']


class CitySuggestionSerializer(serializers.ModelSerializer):
    votes_count = serializers.IntegerField(read_only=True)
    has_voted = serializers.BooleanField(read_only=True)
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = CitySuggestion
        fields = [
            "id",
            "name",
            "country",
            "comment",
            "status",
            "votes_count",
            "has_voted",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_created_by(self, obj):
        if not obj.created_by:
            return None
        return {
            "id": obj.created_by.id,
            "username": obj.created_by.username,
        }

class InterestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Interest
        fields = ['id', 'label', 'description']

class MoodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mood
        fields = ['id', 'label', 'description']
