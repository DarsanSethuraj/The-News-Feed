<?php

if (!defined('ABSPATH')) {
    exit;
}

error_log("PLUGIN FILE LOADED");
error_log("Next scheduled cron job date: " . date('Y-m-d H:i:s', wp_next_scheduled('tnf_fetch_articles_cron')));

require_once ABSPATH . 'wp-admin/includes/media.php';
require_once ABSPATH . 'wp-admin/includes/file.php';
require_once ABSPATH . 'wp-admin/includes/image.php';

add_action('admin_menu', 'tnf_add_admin_menu');
add_action('admin_init', 'tnf_register_settings');

function tnf_add_admin_menu() {
    add_menu_page(
        'The News Feed Settings',
        'The News Feed',
        'manage_options',
        'the-news-feed',
        'tnf_settings_page_html',
        'dashicons-rss',
        20
    );
}

function tnf_register_settings() {
    register_setting('tnf_settings_group', 'tnf_api_key');
    register_setting(
        'tnf_settings_group',
        'tnf_category_map',
        [
            'sanitize_callback' => 'tnf_sanitize_category_map'
        ]
    );
}

function tnf_sanitize_category_map($map) {
    if (!is_array($map)) {
        return [];
    }

    $clean = [];

    foreach ($map as $backend_category => $term_id) {
        $clean[sanitize_text_field($backend_category)] = intval($term_id);
    }

    return $clean;
}




function tnf_settings_page_html() {

    $backend_url = "http://localhost:8000";

    $response = wp_remote_get($backend_url . '/categories', [
        'sslverify' => false,
        'timeout' => 15,
    ]);

    $backend_categories = [];

    if (!is_wp_error($response)) {
        $backend_categories = json_decode(
            wp_remote_retrieve_body($response),
            true
        );
    }

    $wp_categories = get_categories([
        'hide_empty' => false
    ]);

    $category_map = get_option('tnf_category_map', []);

    # Display last feed response for debugging, delete in production
    if ($last_response = get_option('tnf_last_feed_response')): ?>
        <hr>
        <h2>Feed Response</h2>
        <pre><?php echo esc_html($last_response); ?></pre>
    <?php endif; 

    ?>
    <div class="wrap">
        <h1>The News Feed Settings</h1>

        <form method="post" action="options.php">
            <?php settings_fields('tnf_settings_group'); ?>

            <table class="form-table">
                <tr>
                    <th>API Key</th>
                    <td>
                        <input type="text" name="tnf_api_key"
                               value="<?php echo esc_attr(get_option('tnf_api_key')); ?>">
                    </td>
                </tr>
            </table>

            <h2>Category Mapping</h2>

            <table class="form-table">
                <?php foreach ($backend_categories as $backend_category): ?>
                    <tr>
                        <th><?php echo esc_html($backend_category); ?></th>
                        <td>
                            <select name="tnf_category_map[<?php echo esc_attr($backend_category); ?>]">
                                <option value="">Default / Same Name</option>

                                <?php foreach ($wp_categories as $wp_cat): ?>
                                    <option value="<?php echo $wp_cat->term_id; ?>"
                                        <?php selected(
                                            $category_map[$backend_category] ?? '',
                                            $wp_cat->term_id
                                        ); ?>>
                                        <?php echo esc_html($wp_cat->name); ?>
                                    </option>
                                <?php endforeach; ?>

                            </select>
                        </td>
                    </tr>
                <?php endforeach; ?>
            </table>

            <?php submit_button(); ?>
        </form>

    </div>
    <?php
}
