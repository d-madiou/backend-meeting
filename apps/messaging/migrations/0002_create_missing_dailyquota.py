from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('messaging', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                        CREATE TABLE IF NOT EXISTS `daily_message_quotas` (
                            `id` bigint NOT NULL AUTO_INCREMENT,
                            `user_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
                            `date` date NOT NULL,
                            `total_messages_sent` int unsigned NOT NULL DEFAULT 0,
                            `free_messages_used` int unsigned NOT NULL DEFAULT 0,
                            `paid_messages_sent` int unsigned NOT NULL DEFAULT 0,
                            PRIMARY KEY (`id`),
                            UNIQUE KEY `daily_message_quotas_user_date_uniq` (`user_id`,`date`),
                            KEY `daily_message_quotas_user_date_idx` (`user_id`,`date`),
                            CONSTRAINT `daily_message_quotas_user_id_fk` FOREIGN KEY (`user_id`) REFERENCES `users_user` (`id`) ON DELETE CASCADE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            reverse_sql="""
            DROP TABLE IF EXISTS `daily_message_quotas`;
            """,
        ),
    ]
