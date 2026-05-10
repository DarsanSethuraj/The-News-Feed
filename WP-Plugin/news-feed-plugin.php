<?php
/*
Plugin Name: The News Feed
Description: Fetches approved news from backend and posts to WordPress.
Version: 1.0.0
Author: Your Name
*/

if (!defined('ABSPATH')) {
    exit;
}

require_once plugin_dir_path(__FILE__) . 'includes/settings-page.php';


function tnf_fetch_articles() {

    error_log("PLUGIN STARTED");

    $backend_url = "http://localhost:8000";
    $api_key = get_option('tnf_api_key');
    $domain = trailingslashit(home_url());
    
    # STARTING
    $response = wp_remote_get(
        $backend_url . '/feed?api_key=' . urlencode($api_key) . '&domain=' . urlencode($domain),
        [
            'sslverify' => false,
        ]
    );

    error_log(print_r($response, true));

    if (is_wp_error($response)) {
        update_option('tnf_last_feed_response', $response->get_error_message());
        return;
    }

    #ENDING

    $articles = json_decode(wp_remote_retrieve_body($response), true);

    error_log(print_r($articles, true));

    if (!$articles || empty($articles)) {
        update_option('tnf_last_feed_response', 'No new articles found.');
        return;
    }

    $created_count = 0;
    $successfully_posted_ids = [];

    foreach ($articles as $article) {

        $article_hash = md5(
            strtolower(trim($article['title'])) .
            strtolower(trim($article['published_at']))
        );

        $existing_posts = get_posts([
            'post_type'   => 'post',
            'meta_key'    => 'tnf_article_hash',
            'meta_value'  => $article_hash,
            'numberposts' => 1
        ]);

        if (!empty($existing_posts)) {
            update_option(
                'tnf_last_feed_response',
                'Skipped duplicate article ID: ' . $article['id']
            );
            continue;
        }
        

        $source_slug = basename(parse_url($article['link'], PHP_URL_PATH));

        error_log("INSERTING POST");

        $scheduled_time = !empty(
            $article['scheduled_publish_time']
        )
            ? strtotime($article['scheduled_publish_time'])
            : current_time('timestamp');

        if (!$scheduled_time) {
            $scheduled_time = current_time('timestamp');
        }

        $post_id = wp_insert_post([
            'post_title'   => $article['title'],
            'post_content' => wp_kses_post($article['content']),
            'post_status'  => 'future',
            'post_date' => wp_date(
                'Y-m-d H:i:s',
                $scheduled_time
            ),
            'post_date_gmt' => gmdate(
                'Y-m-d H:i:s',
                $scheduled_time
            ),
            'post_type'    => 'post',
            'post_name'    => $source_slug
        ]);

        error_log(print_r($post_id, true));

        if (!is_wp_error($post_id) && $post_id) {

            if (!empty($article['category'])) {

                $category_map = get_option('tnf_category_map', []);
                $backend_category = $article['category'];

                if (!empty($category_map[$backend_category])) {

                    wp_set_post_categories(
                        $post_id,
                        [(int)$category_map[$backend_category]]
                    );

                } else {

                    $term = term_exists($backend_category, 'category');

                    if (!$term) {
                        $term = wp_insert_term($backend_category, 'category');
                    }

                    if (!is_wp_error($term)) {
                        wp_set_post_categories($post_id, [(int)$term['term_id']]);
                    }
                }
            }

            update_post_meta(
                $post_id,
                'tnf_article_hash',
                $article_hash
            );

            error_log("DOWNLOADING IMAGE");

            if (!empty($article['image_url'])) {

                $image_id = media_sideload_image(
                    $article['image_url'],
                    $post_id,
                    null,
                    'id'
                );

                if (!is_wp_error($image_id)) {
                    set_post_thumbnail($post_id, $image_id);
                }
            }
            
            
            $successfully_posted_ids[] = $article['id'];
            
            $created_count++;
        }
    }

    update_option(
        'tnf_last_feed_response',
        "Successfully created {$created_count} post(s)."
    );
    
    if (!empty($successfully_posted_ids)) {

        wp_remote_post(
            $backend_url . '/ack-delivery',
            [
                'headers' => [
                    'Content-Type' => 'application/json'
                ],
                'body' => wp_json_encode([
                    'api_key' => $api_key,
                    'article_ids' => $successfully_posted_ids
                ]),
                'sslverify' => false
            ]
        );
    }
}


add_action('tnf_fetch_articles_cron', 'tnf_fetch_articles');

add_filter('cron_schedules', 'tnf_add_cron_interval');


register_activation_hook(__FILE__, 'tnf_schedule_cron');
register_deactivation_hook(__FILE__, 'tnf_unschedule_cron');


function tnf_add_cron_interval($schedules) {
    $schedules['five_minutes'] = [
        'interval' => 300,       # change to 300 for 5 minutes in production
        'display'  => 'Every 5 Minutes'
    ];

    return $schedules;
}


function tnf_schedule_cron() {
    if (!wp_next_scheduled('tnf_fetch_articles_cron')) {
        wp_schedule_event(time(), 'five_minutes', 'tnf_fetch_articles_cron');
    }
}


function tnf_unschedule_cron() {
    $timestamp = wp_next_scheduled('tnf_fetch_articles_cron');

    if ($timestamp) {
        wp_unschedule_event($timestamp, 'tnf_fetch_articles_cron');
    }
}