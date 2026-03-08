from django.db import migrations, models


def seed_default_interests(apps, schema_editor):
    Interest = apps.get_model('users', 'Interest')
    default_interests = [
        'Cooking',
        'Travel',
        'Reading',
        'Sports',
        'Music',
        'Technology',
        'Movies',
        'Entrepreneurship',
        'Fitness',
        'Volunteering',
    ]

    for name in default_interests:
        Interest.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='religion',
            field=models.CharField(
                choices=[
                    ('muslim', 'Muslim'),
                    ('christian', 'Christian'),
                    ('hindu', 'Hindu'),
                    ('buddhist', 'Buddhist'),
                    ('traditional', 'Traditional'),
                    ('other', 'Other'),
                ],
                help_text='Select one religion option',
                max_length=100,
            ),
        ),
        migrations.RunPython(seed_default_interests, migrations.RunPython.noop),
    ]
