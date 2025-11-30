# Previewing converted fonts

After building a Language Pack generated fonts will be placed in `build` directory as files `001` to `008`. You can preview them in Pebble SDK's emulator before sending the generated `.pbl` file to your phone and watch.

> ❗ Very big font files may fail to load into watchapp allowed memory area.

## Create a test Pebble watchapp

Set up the [SDK](https://developer.rebble.io/sdk/) and create a new project.

Replace the code in the main `.c` file and change preview characters:

<details>

<summary>project-name.c</summary>

```c
#include <pebble.h>

static Window *s_window;
static TextLayer *s_text_layer;

static GFont s_custom_font;

static void prv_window_load(Window *window) {
  Layer *window_layer = window_get_root_layer(window);
  GRect bounds = layer_get_bounds(window_layer);

  s_text_layer = text_layer_create(GRect(0, 72, bounds.size.w, 28)); // resize height (28) accordingly
  s_custom_font = fonts_load_custom_font(resource_get_handle(RESOURCE_ID_001_pbf)); 
  text_layer_set_font(s_text_layer, s_custom_font);
  text_layer_set_text(s_text_layer, "<put your characters to preview>");
  text_layer_set_text_alignment(s_text_layer, GTextAlignmentCenter);
  layer_add_child(window_layer, text_layer_get_layer(s_text_layer));
}

static void prv_window_unload(Window *window) {
  text_layer_destroy(s_text_layer);
  fonts_unload_custom_font(s_custom_font);
}

static void prv_init(void) {
  s_window = window_create();
  window_set_window_handlers(s_window, (WindowHandlers) {
    .load = prv_window_load,
    .unload = prv_window_unload,
  });
  const bool animated = true;
  window_stack_push(s_window, animated);
}

static void prv_deinit(void) {
  window_destroy(s_window);
}

int main(void) {
  prv_init();
  app_event_loop();
  prv_deinit();
}
```

</details>
<br>

Create a folder `resources/` in the project root folder. Copy one of the generated PBF font files there, `001` for example, and add the a resources media entry in `package.json` for it:

<details>

<summary>package.json</summary>

```json
{
    ...
    "pebble": {
        ...
        "resources": {
            "media": [
                {
                    "type": "raw",
                    "name": "001_pbf",
                    "file": "001"
                }
            ]
        }
    }
}
```

</details>
<br>

Build and run the project in an emulator to preview your font:

```
pebble build && pebble install --emulator diorite
```

Note that if you included only non-Latin characters in your Language Pack (which is totally OK) the emulator won't be able to show Basic Latin subset of characters from the provided PBF file. Basic Latin subset includes Latin letters, space (` `), digits, common punctuation symbols, etc.
